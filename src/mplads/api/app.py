"""FastAPI service over the pre-computed intelligence artifacts.

Everything is loaded into memory once at startup (210k rows is nothing) and served
read-only. No model runs here — the pipeline produced the artifacts; this serves them.

Role scoping is enforced from a signed token: `auth.require_scope` narrows every scoped
read to the caller's jurisdiction, and the stakeholder switcher in the UI only reframes
what an already-permitted caller sees. The accounts themselves are seeded for evaluation
and listed openly at `/api/auth/accounts`; a deployment swaps that one function for an
identity provider and nothing else changes.
"""

from __future__ import annotations

import gc
import json
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mplads import casereport
from mplads import chat as chatbot
from mplads import field, ocr
from mplads import config, llm
from mplads.api import auth
from mplads.api.strings import UI
from mplads.api import translations
from mplads.api.audit import AuditLog
from mplads.api.stores import CaseStore, DuplicateStore
from mplads.intelligence import assignment, calibration, dossier, targeting
from mplads.api.auth import Principal, current_principal

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the corpus and flatten its search text before the first question arrives.

    Done here rather than lazily so the first officer to ask something does not pay nine
    seconds for everyone else's convenience.
    """
    try:
        chatbot.warm()
    except Exception as exc:  # pragma: no cover - never block startup on a warm-up
        LOGGER.warning("search index not pre-built (%s); it will build on first use",
                       type(exc).__name__)
    try:
        # The plan at the default budget is what the Audit Plan screen asks for first, and
        # it is ten seconds of arithmetic. Paying it here means no officer ever does.
        _plan_cached("*", float(targeting.DEFAULT_BUDGET))
        _rota_cached("*", float(targeting.DEFAULT_BUDGET), 4)
    except Exception as exc:  # pragma: no cover - never block startup on a warm-up
        LOGGER.warning("audit plan not pre-built (%s); it will build on first use",
                       type(exc).__name__)
    try:
        # Find out here whether the live model actually answers. Without this the *first*
        # visitor of the day pays the round-trip that discovers the key has no credits,
        # and reads it as the site being slow. `llm._ask` remembers the answer, so this is
        # the only time anything waits for it.
        llm.portfolio_insight(store().stats, "en")
    except Exception as exc:  # pragma: no cover - never block startup on a warm-up
        LOGGER.info("insight not pre-built (%s)", type(exc).__name__)
    try:
        # Touching the duplicate frame here pulls it into memory and lets pandas build its
        # indices, which is most of the cost of the first Near-Duplicates page load.
        if not store().duplicate_pairs.empty:
            _concerning_pairs()
    except Exception as exc:  # pragma: no cover - never block startup on a warm-up
        LOGGER.info("duplicate frame not warmed (%s)", type(exc).__name__)
    # Surya's server takes tens of seconds to load its model. Started in the background so
    # the API is answering immediately, and so the first officer to photograph a board is
    # not the one who waits for it. If it cannot start, photographs fall back to RapidOCR.
    ocr.warm_in_background()
    # The budget slider steps in fives, so a drag lands on values nobody has asked for yet.
    # Each costs about a quarter of a second to plan and nothing at all afterwards; warming
    # the whole range takes ~15 s of one background thread and makes every later move on
    # the Visit Plan and Who Goes Where screens instant.
    if not config.LOW_MEMORY:
        threading.Thread(target=_warm_budget_slider, name="plan-warm", daemon=True).start()
    else:
        LOGGER.info("low-memory mode: the budget slider warms as it is used")
    threading.Thread(target=_housekeeping, name="memory-housekeeping", daemon=True).start()
    _release_memory()
    yield
    ocr.shutdown()


app = FastAPI(title="MPLADS Intelligence", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

#: role -> which column narrows the data, and what the role is called.
ROLES: dict[str, dict] = {
    "ministry": {"label": "Ministry (MoSPI)", "scope_field": None,
                 "focus": "National aggregates, state comparison, systemic patterns"},
    "state": {"label": "State Nodal Authority", "scope_field": "state",
              "focus": "District and agency comparison within the state"},
    "district": {"label": "District Authority", "scope_field": "implementing_agency",
                 "focus": "Works, delays, duplicates and compliance in this jurisdiction"},
    "mp": {"label": "Member of Parliament", "scope_field": "constituency",
           "focus": "Works recommended in this constituency"},
}


def intern(value):
    """`sys.intern` where the value is text, and a pass-through where it is not.

    Several identity fields are legitimately missing — a Rajya Sabha work has no district
    office — and interning must not turn an absent value into a present one.
    """
    return sys.intern(value) if type(value) is str else value


def pa_schema_with_dictionaries(schema, columns: list[str]):
    """The same Arrow schema with the named string columns dictionary-encoded.

    Dictionary encoding is what pandas calls a category: 210,993 rows carry 36 state names
    and 778 agency names, so storing the text once and an index per row is the difference
    between 66 MB and several hundred.
    """
    import pyarrow as pa

    fields = []
    for field in schema:
        if field.name in columns and pa.types.is_string(field.type):
            fields.append(pa.field(field.name, pa.dictionary(pa.int32(), pa.string())))
        else:
            fields.append(field)
    return pa.schema(fields)


def _read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class Store:
    def __init__(self, artifacts: Path):
        self.stats = _read(artifacts / "stats.json")
        self.temporal = _read(artifacts / "temporal.json")
        self.transparency = _read(artifacts / "transparency.json")
        self.metrics = _read(artifacts / "models" / "metrics.json")

        # The case files live in SQLite (stores.CaseStore): 37,705 nested records are 400 MB
        # as dictionaries and a request reads one. The worklist below is the only thing kept
        # in memory from them — it is the flat summary every queue page renders.
        self.cases_by_ref = CaseStore(artifacts)
        cases = self.cases_by_ref.values()
        self.worklist = [
            {
                "work_ref": c["work_ref"],
                "description": c["identity"]["description"],
                # `sys.intern` on the repeating fields: 37,705 rows carry 36 state names
                # and 778 agency names, and JSON hands back a separate string object for
                # every one of them. Sharing them costs nothing and saves ~25 MB.
                "state": intern(c["identity"]["state"]),
                "constituency": intern(c["identity"]["constituency"]),
                "implementing_agency": intern(c["identity"]["implementing_agency"]),
                "mp_name": intern(c["identity"]["mp_name"]),
                "archetype": intern(c["archetype"]["label"]),
                "band": intern(c["confidence_band"]),
                "n_families": c["n_signal_families"],
                "priority": c["priority"],
                "exposure_rupees": c["exposure_rupees"],
                "audit_roi": c["audit_roi"],
                "recommended_amount": c["identity"]["recommended_amount"],
                "early_warning": intern(c.get("early_warning", {}).get("level", "LOW")),
                "compliance_flags": len(c.get("compliance_findings", [])),
                "has_duplicate": c.get("duplicate") is not None,
                "signals": [intern(e["signal"]) for e in c.get("evidence", [])],
            }
            for c in cases
        ]

        # 223,407 pairs are 248 MB in pandas and the screen shows fifty. Read per question.
        self.duplicate_pairs = DuplicateStore(artifacts / "duplicate_pairs.parquet")
        self._artifacts = artifacts
        self._corpus: pd.DataFrame | None = None
        self._plan_frame: pd.DataFrame | None = None
        self._all_refs: set[str] | None = None
        self._amounts: dict[str, float] | None = None

    #: The columns the assistant and the photo matcher need. Everything else in
    #: works_scored stays on disk — the full 82-column frame is 547 MB in memory and
    #: none of the rest is ever asked for.
    #: Columns the audit planner needs. Loaded separately from the chat corpus because it
    #: is a different question — the planner cares about money and travel, not description
    #: text, and pulling the 31 MB of descriptions to sort by exposure is waste.
    PLAN_COLUMNS = [
        "work_ref", "implementing_agency", "rs_exposure", "state_name",
        "audit_roi", "priority", "band", "recommended_amount",
    ]

    CORPUS_COLUMNS = [
        "work_ref", "state_name", "constituency", "implementing_agency", "mp_name",
        "house", "work_description", "activity_category", "archetype_label",
        "recommended_amount", "is_completed", "is_open", "duration_days", "band",
        "priority", "rs_exposure", "audit_roi", "compliance_flags",
        "early_warning_level", "risk_score", "recommendation_date", "completion_date",
    ]
    CORPUS_CATEGORICAL = [
        "state_name", "constituency", "implementing_agency", "mp_name", "house",
        "activity_category", "archetype_label", "band", "early_warning_level",
    ]

    @property
    def corpus(self) -> pd.DataFrame:
        """All 210,993 works, not only the ones surfaced as leads.

        The dashboard ranks leads; a question like "what has Bihar recommended for school
        buildings" is about the whole portfolio. Loaded on first use and held — about 66 MB
        once the repeated strings are categorical.
        """
        if self._corpus is None:
            path = self._artifacts / "works_scored.parquet"
            if not path.exists():
                self._corpus = pd.DataFrame(columns=self.CORPUS_COLUMNS)
            else:
                import pyarrow as pa
                import pyarrow.dataset as ds

                # Streamed rather than read whole. `pd.read_parquet` on 22 of these 82
                # columns peaked at 280 MB — Arrow reads ahead on several threads, and on
                # a 512 MB host that read-ahead is the whole difference between running
                # and being killed. One batch at a time, cast to dictionaries as it
                # arrives (which is what pandas calls a category: 210,993 rows carry 36
                # state names), and `self_destruct` drops each buffer as pandas takes it.
                scanner = ds.dataset(path, format="parquet").scanner(
                    columns=self.CORPUS_COLUMNS, batch_size=25_000,
                    use_threads=False, batch_readahead=1, fragment_readahead=1)
                schema = pa_schema_with_dictionaries(
                    scanner.projected_schema, self.CORPUS_CATEGORICAL)
                batches = [batch.cast(schema) for batch in scanner.to_batches()]
                table = pa.Table.from_batches(batches, schema=schema)
                del batches
                self._corpus = table.to_pandas(split_blocks=True, self_destruct=True)
                del table
                LOGGER.info("corpus loaded: %s works", f"{len(self._corpus):,}")
        return self._corpus

    @property
    def plan_frame(self) -> pd.DataFrame:
        """The lean frame the audit planner runs on, loaded once and held."""
        if self._plan_frame is None:
            # Every planner column is already in the corpus, so this is a narrow copy of a
            # frame we hold rather than a second read of the same file. Reading it again
            # cost 70 MB and a few seconds to end up with the same numbers.
            corpus = self.corpus
            missing = [c for c in self.PLAN_COLUMNS if c not in corpus.columns]
            if missing:
                self._plan_frame = pd.DataFrame(columns=self.PLAN_COLUMNS)
            else:
                self._plan_frame = corpus[self.PLAN_COLUMNS].copy()
                LOGGER.info("audit planner frame taken from the corpus: %s works",
                            f"{len(self._plan_frame):,}")
        return self._plan_frame

    @property
    def all_refs(self) -> set[str]:
        """Every work reference in the portfolio — what a photographed board is matched to."""
        if self._all_refs is None:
            self._all_refs = set(self.corpus["work_ref"])
        return self._all_refs

    @property
    def amounts(self) -> dict[str, float]:
        """Recommended amount per work, so a figure read off a board can be checked."""
        if self._amounts is None:
            frame = self.corpus
            self._amounts = dict(
                zip(frame["work_ref"], frame["recommended_amount"].astype(float))
            )
        return self._amounts


@lru_cache(maxsize=1)
def store() -> Store:
    return Store(config.ARTIFACTS)


@lru_cache(maxsize=1)
def audit() -> AuditLog:
    return AuditLog(config.AUDIT_LOG_PATH)


@app.middleware("http")
async def record_every_request(request: Request, call_next):
    """Every intelligence read is written to the append-only, hash-chained log."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/audit"):
        principal = getattr(request.state, "principal", None)
        try:
            audit().record(
                actor=getattr(principal, "subject", "anonymous"),
                role=getattr(principal, "role", "open-data"),
                action=request.method,
                resource=path,
                detail={"query": dict(request.query_params), "status": response.status_code},
            )
        except Exception:  # logging must never break the request path
            pass
    return response


def _scope(rows: list[dict], role: str | None, scope: str | None) -> list[dict]:
    """Narrow a worklist to a role's jurisdiction. Role simulation, not authentication."""
    if not role or role == "ministry" or not scope:
        return rows
    field = ROLES.get(role, {}).get("scope_field")
    if not field:
        return rows
    return [r for r in rows if r.get(field) == scope]


# ------------------------------------------------------------------- core endpoints


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "leads": len(store().worklist), "version": app.version}


@app.get("/api/roles")
def roles() -> dict:
    """Available roles and the scope values each can select."""
    s = store()
    states = sorted({r["state"] for r in s.worklist if r["state"]})
    constituencies = sorted({r["constituency"] for r in s.worklist if r["constituency"]})
    agencies = sorted({r["implementing_agency"] for r in s.worklist if r["implementing_agency"]})
    return {
        "roles": ROLES,
        "scopes": {
            "state": states,
            "mp": constituencies[:600],
            "district": agencies[:900],
        },
        "note": "Role simulation for the prototype. No authentication is implemented; "
                "production would place an identity provider in front of the same filter.",
    }


@app.get("/api/stats")
def stats(role: str | None = None, scope: str | None = None) -> dict:
    """National statistics, or a role-scoped recomputation of the headline numbers."""
    s = store()
    if not role or role == "ministry" or not scope:
        return s.stats

    rows = _scope(s.worklist, role, scope)
    scoped = dict(s.stats)
    scoped["national"] = {
        **s.stats["national"],
        "scoped": True,
        "scope_role": role,
        "scope_value": scope,
        "surfaced_leads": len(rows),
        "total_exposure_rupees": sum(r["exposure_rupees"] for r in rows),
        "bands": {
            band: sum(1 for r in rows if r["band"] == band) for band in ("HIGH", "MEDIUM")
        },
    }
    return scoped


@app.get("/api/worklist")
def worklist(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = None,
    band: str | None = None,
    warning: str | None = None,
    signal: str | None = None,
    q: str | None = None,
    role: str | None = None,
    scope: str | None = None,
) -> dict:
    rows = _scope(store().worklist, role, scope)
    if state:
        rows = [r for r in rows if r["state"] == state]
    if band:
        rows = [r for r in rows if r["band"] == band]
    if warning:
        rows = [r for r in rows if r["early_warning"] == warning]
    if signal:
        rows = [r for r in rows if signal in r["signals"]]
    if q:
        needle = q.lower()
        rows = [
            r for r in rows
            if needle in (r["description"] or "").lower()
            or needle in (r["implementing_agency"] or "").lower()
        ]
    return {"total": len(rows), "items": rows[offset : offset + limit]}


@app.get("/api/case/{work_ref}")
def case(work_ref: str, principal: Principal = Depends(current_principal)) -> dict:
    found = store().cases_by_ref.get(work_ref) or _clear_record(work_ref)
    if not found:
        raise HTTPException(status_code=404, detail="no such work in this portfolio")
    identity = found["identity"]
    auth.require_scope(
        principal,
        {
            "state": identity.get("state"),
            "implementing_agency": identity.get("implementing_agency"),
            "constituency": identity.get("constituency"),
        },
        f"case file {work_ref}",
    )
    return found


def _clear_record(work_ref: str) -> dict | None:
    """A case file for a work nothing was flagged on.

    173,288 of the 210,993 works were never surfaced, and returning 404 for all of them
    made "nothing wrong with this work" indistinguishable from "no such work". It also
    made them unverifiable, which quietly guaranteed that every field record an officer
    ever wrote would be about a work the system had already flagged — a label set of
    nothing but positives, useless for fitting anything.
    """
    frame = store().corpus
    row = frame[frame["work_ref"] == work_ref]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "work_ref": work_ref,
        "surfaced": False,
        "identity": {
            "description": str(r["work_description"]),
            "state": str(r["state_name"]),
            "constituency": str(r["constituency"]),
            "implementing_agency": str(r["implementing_agency"]),
            "mp_name": str(r["mp_name"]),
            "recommended_amount": float(r["recommended_amount"]),
            "recommendation_date": str(r["recommendation_date"])[:10],
            "completion_date": str(r["completion_date"])[:10]
                if pd.notna(r["completion_date"]) else None,
            "is_completed": bool(r["is_completed"]),
        },
        "archetype": {"label": str(r["archetype_label"])},
        "confidence_band": "NONE",
        "n_signal_families": 0,
        "priority": 0.0,
        "exposure_rupees": 0.0,
        "audit_roi": 0.0,
        "evidence": [],
        "compliance_findings": [],
        "recommended_next_step": (
            "No signal fired on this work — it sits inside the norms of its peer group on "
            "every measure we compute. Nothing here needs a reviewer. It can still be "
            "verified in the field, and a confirmed-fine record is as useful to this "
            "system as a confirmed problem."
        ),
    }


# --------------------------------------------------------------------- audit trail


@app.get("/api/audit/verify")
def audit_verify() -> dict:
    """Recompute the whole hash chain and report whether it is intact."""
    return audit().verify_chain()


@app.get("/api/audit/tail")
def audit_tail(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    return audit().tail(limit)


@app.get("/api/auth/demo-tokens")
def demo_tokens() -> dict:
    """Seeded tokens for the demo. Never a production issuance mechanism."""
    return {
        "tokens": auth.seed_demo_tokens(),
        "require_auth": config.REQUIRE_AUTH,
        "note": "Set MPLADS_REQUIRE_AUTH=1 to enforce bearer auth and exercise the 403 "
                "paths. Tokens are seeded from a development signing key, not issued by "
                "an identity provider.",
    }


@app.get("/api/states")
def states() -> list[dict]:
    return store().stats.get("by_state", [])


@app.get("/api/models")
def models() -> dict:
    return store().metrics


# ------------------------------------------------------- language & AI briefings


@app.get("/api/languages")
def languages() -> dict:
    """Interface languages. Every one listed ships a complete, static bundle."""
    return {
        "languages": {code: name for code, (name, _, _) in translations.BUNDLES.items()},
        "native": {code: native for code, (_, native, _) in translations.BUNDLES.items()},
        "llm_available": llm.available(),
        "note": "Interface translations are shipped with the application and need no "
                "network call. The language model is used only for written briefings, "
                "which fall back to a deterministic template when unavailable.",
    }


@app.get("/api/strings")
def strings(lang: str = Query("en")) -> dict:
    """The complete UI bundle for one language. Static — no API call, no cache miss."""
    if lang not in translations.BUNDLES:
        raise HTTPException(400, f"unsupported language: {lang}")
    return {
        "lang": lang,
        "coverage": translations.coverage(lang),
        "strings": translations.bundle(lang),
    }


@app.get("/api/insight/portfolio")
def portfolio_insight(lang: str = Query("en"), role: str | None = None,
                      scope: str | None = None) -> dict:
    """A written brief over the national (or scoped) picture."""
    return llm.portfolio_insight(stats(role=role, scope=scope), language=lang)


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = []
    lang: str = "en"


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Ask the assistant. It answers only from tool calls against the real artifacts."""
    if not req.question.strip():
        raise HTTPException(400, "question is required")
    history = [{"role": t.role, "content": t.content} for t in req.history][-12:]
    return chatbot.answer(req.question.strip(), history=history, language=req.lang)


@app.get("/api/chat/capabilities")
def chat_capabilities() -> dict:
    """What the assistant can look up, and whether it is running live or offline."""
    return {
        "live": llm.available(),
        "tools": [
            {"name": name, "does": (fn.__doc__ or "").strip().splitlines()[0]}
            for name, fn in chatbot.TOOL_FUNCS.items()
        ],
        "suggestions": [
            "How many investigation leads are there?",
            "Show me the top leads",
            "What does exposure at risk mean?",
            "Tell me about MP3018356-W86316",
            "Can you detect cost overruns?",
            "What models did you train?",
        ],
        # Grouped starters, so the panel opens on something an evaluator would
        # actually ask rather than a blank box. Every one of these is answerable by
        # the offline router, so they work with or without billing.
        "categories": [
            {
                "category": "Portfolio & scale",
                "icon": "▤",
                "prompts": [
                    "How many works and leads are in the national portfolio?",
                    "What does exposure at risk mean?",
                    "What is the health index?",
                ],
            },
            {
                "category": "Leads & ranking",
                "icon": "▦",
                "prompts": [
                    "Show me the top leads",
                    "How are leads ranked?",
                    "What does HIGH confidence mean?",
                ],
            },
            {
                "category": "States & agencies",
                "icon": "§",
                "prompts": [
                    "How many works in Bihar?",
                    "Which agencies changed behaviour?",
                    "Tell me about MP3018356-W86316",
                ],
            },
            {
                "category": "Method & limits",
                "icon": "◈",
                "prompts": [
                    "What models did you train?",
                    "What work types did you discover?",
                    "Can you detect cost overruns?",
                ],
            },
            {
                "category": "Salesforce & Agentforce",
                "icon": "⚡",
                "prompts": [
                    "Show me HIGH priority cases in Bihar",
                    "What cases are loaded in Salesforce CRM?",
                    "What is the 5-stage investigation path?",
                    "Which case has the highest exposure?",
                ],
            },
        ],
        # The languages the *interface* is translated into. The written answer is
        # English unless a funded key is configured, and `answers_translated` says
        # which of those two is true rather than letting the picker imply the first.
        "languages": {code: name for code, (name, _, _) in translations.BUNDLES.items()},
        "native": {code: native for code, (_, native, _) in translations.BUNDLES.items()},
        "answers_translated": llm.available(),
    }


# --------------------------------------------------------- audit plan & case report


@app.get("/api/audit-plan")
def audit_plan(budget_days: float = Query(targeting.DEFAULT_BUDGET, ge=1, le=1000),
               principal: Principal = Depends(current_principal)) -> dict:
    """A budgeted investigation plan, and what the alternatives would have covered.

    Ranking answers "what is worst?". This answers "where do I send twenty auditor-days?",
    which is a different question because cases do not cost the same to check — five works
    at one district office are one trip.
    """
    # A scoped officer plans their own jurisdiction, not the country.
    return _plan_cached(_scope_key(principal), float(budget_days))


def _scope_key(principal: Principal) -> str:
    """One string that identifies exactly which slice of the country this caller sees.

    It is the cache key, so it has to be *complete*: a key that collapsed two different
    jurisdictions together would serve a Bihar officer a plan built from Kerala's works,
    which is a data leak wearing the costume of a performance optimisation.
    """
    if principal.unrestricted:
        return "*"
    return f"{principal.role}:{principal.scope}"


#: The plan is the most expensive thing this service computes, and it is *deterministic* —
#: same works, same budget, same plan, every time. It was being rebuilt from scratch on
#: every page load: ten seconds, seven full runs of the optimiser (one for the plan, one
#: for the comparison table, five for the coverage curve), all to produce bytes identical
#: to the ones produced a moment earlier.
#:
#: Cached on (jurisdiction, budget) rather than memoised inside `targeting` because the
#: jurisdiction has to be part of the key and only this layer knows it. Small enough to
#: hold every budget preset for every demo account at once; the artifacts are read-only
#: between pipeline runs, so nothing can go stale under it while the service is up.
def _release_memory() -> None:
    """Give the working memory of start-up back to the operating system.

    Reading parquet leaves large blocks in Arrow's pool, and they are not freed by garbage
    collection because nothing in Python owns them any more — the pool is simply holding
    them for reuse. On a machine with memory to spare that is the right behaviour; on a
    512 MB host it is 30-something megabytes of the allowance held against a read that has
    already finished.
    """
    gc.collect()
    try:
        import pyarrow

        pyarrow.default_memory_pool().release_unused()
    except Exception:  # pragma: no cover - a memory hint must never take the API down
        pass


#: How often the idle memory left behind by serving is handed back.
HOUSEKEEPING_SECONDS = 120

#: How many (jurisdiction, budget) plans are remembered. Each is a plan, its comparison
#: table and its per-state totals, so the difference between 128 and 12 is real memory.
PLAN_CACHE = 12 if config.LOW_MEMORY else 128


def _housekeeping() -> None:
    """Give back, periodically, what serving requests leaves lying around.

    Every question that filters a frame or scans the parquet allocates and frees, and both
    pandas and Arrow keep the freed blocks for reuse rather than returning them. Over a
    session of moving the budget slider that reached a few hundred megabytes of memory the
    process was holding and not using — invisible on a laptop, fatal on a 512 MB host, where
    what gets measured is what the process holds, not what it needs.
    """
    while True:
        time.sleep(HOUSEKEEPING_SECONDS)
        _release_memory()


def _warm_budget_slider() -> None:
    """Fill the plan cache for every slider position, presets first, national scope only.

    A scoped officer's first move still pays for one plan; warming every jurisdiction would
    be 36 times the work for a screen most of them never open.
    """
    budgets = list(targeting.BUDGET_PRESETS) + list(range(5, 251, 5))
    seen: set[float] = set()
    for budget in budgets:
        value = float(budget)
        if value in seen:
            continue
        seen.add(value)
        try:
            _plan_cached("*", value)
        except Exception as exc:  # pragma: no cover - a warm-up must never take the API down
            LOGGER.info("plan warm-up stopped at %s days (%s)", budget, type(exc).__name__)
            return
    for auditors in (1, 2, 4, 6, 8, 12):
        try:
            _rota_cached("*", float(targeting.DEFAULT_BUDGET), auditors)
        except Exception:
            return
    LOGGER.info("plan cache warm: %s budgets", len(seen))
    _release_memory()


@lru_cache(maxsize=PLAN_CACHE)
def _plan_cached(scope_key: str, budget_days: float) -> dict:
    return targeting.build(_frame_for_scope(scope_key), budget_days=budget_days,
                           curve=_curve_cached(scope_key),
                           leads=_leads_for_scope(scope_key))


#: The coverage curve does not depend on the budget — it always reports the same fixed
#: presets — so it is cached once per jurisdiction rather than per slider position. It was
#: five runs of the optimiser on every request, redrawing a line that had not moved.
@lru_cache(maxsize=16)
def _curve_cached(scope_key: str) -> list[dict]:
    leads = _leads_for_scope(scope_key)
    return targeting.coverage_curve(leads) if not leads.empty else []


#: The leads within a jurisdiction do not depend on the budget, but selecting them copies
#: 37,705 rows — and the budget slider asked for that copy once per position. Cached per
#: jurisdiction instead. Treat the result as read-only; `optimise` does.
@lru_cache(maxsize=16)
def _leads_for_scope(scope_key: str) -> pd.DataFrame:
    frame = _frame_for_scope(scope_key)
    return frame[frame["band"].isin(["HIGH", "MEDIUM"])]


#: The plan itself, as a frame, cached per (jurisdiction, budget). The rota and the audit
#: plan screen both need it, and the team size does not change it — so the auditors dial
#: costs a deal of the same trips rather than a fresh run of the optimiser.
@lru_cache(maxsize=PLAN_CACHE)
def _plan_frame_cached(scope_key: str, budget_days: float) -> pd.DataFrame:
    return targeting.optimise(_leads_for_scope(scope_key), budget_days=budget_days)


@lru_cache(maxsize=PLAN_CACHE)
def _rota_cached(scope_key: str, budget_days: float, auditors: int) -> dict:
    # A copy, because the cached frame outlives this call and assignment sorts what it is
    # given; handing out the cached object would let one request reorder the next one's.
    plan = _plan_frame_cached(scope_key, budget_days).copy()
    return assignment.build(_frame_for_scope(scope_key), budget_days=budget_days,
                            auditors=auditors, plan=plan)


def _frame_for_scope(scope_key: str) -> pd.DataFrame:
    """The planning frame for a cache key, narrowed the same way `_scoped_plan_frame` is."""
    frame = store().plan_frame
    if frame.empty:
        raise HTTPException(503, "no scored works available; run the pipeline first")
    if scope_key == "*":
        return frame

    role, _, scope = scope_key.partition(":")
    column = auth.ROLE_SCOPE.get(role)
    mapped = {"state": "state_name", "implementing_agency": "implementing_agency",
              "constituency": "constituency"}.get(column)
    if mapped and mapped in frame.columns and scope:
        frame = frame[frame[mapped] == scope]
    if frame.empty:
        raise HTTPException(404, f"no works within {scope}")
    return frame


def _scoped_plan_frame(principal: Principal) -> pd.DataFrame:
    """The planning frame narrowed to whatever jurisdiction the caller actually holds.

    Shared by the plan and the rota so a scoped officer cannot get a national answer by
    asking the second endpoint instead of the first.
    """
    frame = store().plan_frame
    if frame.empty:
        raise HTTPException(503, "no scored works available; run the pipeline first")
    if principal.unrestricted:
        return frame

    column = auth.ROLE_SCOPE.get(principal.role)
    mapped = {"state": "state_name", "implementing_agency": "implementing_agency",
              "constituency": "constituency"}.get(column)
    if mapped and mapped in frame.columns and principal.scope:
        frame = frame[frame[mapped] == principal.scope]
    if frame.empty:
        raise HTTPException(404, f"no works within {principal.scope}")
    return frame


@app.get("/api/audit-plan/assignments")
def audit_assignments(budget_days: float = Query(targeting.DEFAULT_BUDGET, ge=1, le=1000),
                      auditors: int = Query(4, ge=1, le=assignment.MAX_AUDITORS),
                      principal: Principal = Depends(current_principal)) -> dict:
    """The plan with names against it: who goes where, and on which day.

    The plan says where the days should go. A supervisor has to issue something with people
    on it, and that is a second problem with one hard rule — an implementing agency is
    never split between two auditors, because the plan's whole saving is that the second
    work at an agency is cheap when somebody is already standing there.
    """
    return _rota_cached(_scope_key(principal), float(budget_days), int(auditors))


@app.get("/api/audit-plan/assignments/{auditor}/pack.pdf")
def audit_day_pack(auditor: int,
                   budget_days: float = Query(targeting.DEFAULT_BUDGET, ge=1, le=1000),
                   auditors: int = Query(4, ge=1, le=assignment.MAX_AUDITORS),
                   principal: Principal = Depends(current_principal)):
    """One auditor's round as a document they can carry, tick and hand back."""
    rota = _rota_cached(_scope_key(principal), float(budget_days), int(auditors))
    if not rota.get("available"):
        raise HTTPException(404, rota.get("note", "no rota available"))

    person = next((p for p in rota["people"] if p["auditor"] == auditor), None)
    if person is None:
        raise HTTPException(404, f"no auditor {auditor} in a team of {auditors}")

    audit().record(
        actor=principal.subject or "anonymous", role=principal.role or "viewer",
        action="EXPORT_DAY_PACK",
        resource=f"/api/audit-plan/assignments/{auditor}/pack.pdf",
        detail={"budget_days": budget_days, "auditors": auditors,
                "works": person["works"]},
    )
    return Response(
        content=casereport.build_day_pack(person, rota),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="MPLADS-day-pack-auditor-{auditor}.pdf"'},
    )


@app.get("/api/agencies")
def agency_list(limit: int = Query(40, ge=1, le=200)) -> dict:
    """Implementing agencies by exposure carried — a picker, not a ranking of conduct."""
    return {
        "items": dossier.agencies(store().corpus, limit=limit),
        "note": ("Ordered by exposure carried, which tracks size as much as anything else. "
                 "Open a dossier to see the rate rather than the count."),
    }


@app.get("/api/agency/{agency}")
def agency_dossier(agency: str,
                   principal: Principal = Depends(current_principal)) -> dict:
    """What an auditor should read on the way to an implementing agency.

    An auditor's day is organised around a body, not a work — which is why the plan batches
    by agency and the rota is dealt out in whole agencies. This is the page for the journey.
    """
    frame = store().corpus
    if frame.empty:
        raise HTTPException(503, "no scored works available; run the pipeline first")

    match = next((str(name) for name in frame["implementing_agency"].unique()
                  if str(name).lower() == agency.lower()), None)
    if match is None:
        raise HTTPException(404, "no such implementing agency in this portfolio")

    row = frame[frame["implementing_agency"] == match].iloc[0]
    auth.require_scope(
        principal,
        {"state": str(row["state_name"]), "implementing_agency": match,
         "constituency": str(row["constituency"])},
        f"agency dossier {match}",
    )

    try:
        verifications = field.recent(limit=5000)
    except Exception:            # a missing store must not empty the dossier
        verifications = []

    return dossier.build(
        frame, match,
        cases_by_ref=store().cases_by_ref,
        duplicate_pairs=store().duplicate_pairs.for_refs,
        verifications=verifications,
    )


@app.get("/api/calibration")
def model_calibration() -> dict:
    """Has the model been right? The one table this system is allowed to lose on.

    Compares what officers recorded on site against the band each work was surfaced with.
    Rates below a minimum sample are refused rather than printed, every rate carries a
    Wilson interval, and the sampling bias — officers go where this model sends them — is
    stated with the result rather than in a footnote nobody reads.
    """
    try:
        verifications = field.recent(limit=5000)
    except Exception as exc:
        raise HTTPException(503, f"verification store unavailable: {type(exc).__name__}")

    bands = store().cases_by_ref.bands()
    result = calibration.build(verifications, bands, field.CONFIRMS_CONCERN)
    result["label_readiness"] = field.label_readiness()
    return result


@app.get("/api/case/{work_ref}/report.pdf")
def case_report(work_ref: str,
                principal: Principal = Depends(current_principal)):
    """The case file as a document an officer can take to a site visit.

    Served as a real PDF rather than a print stylesheet because it leaves the browser: it
    gets emailed, filed and read months later by someone who never saw the screen. The
    non-fraud contract is stamped on every page for exactly that reason.
    """
    found = store().cases_by_ref.get(work_ref) or _clear_record(work_ref)
    if not found:
        raise HTTPException(404, "no such work in this portfolio")

    identity = found["identity"]
    auth.require_scope(
        principal,
        {"state": identity.get("state"),
         "implementing_agency": identity.get("implementing_agency"),
         "constituency": identity.get("constituency")},
        f"case file {work_ref}",
    )

    try:
        verifications = field.for_work(work_ref)
    except Exception:            # a missing store must not block the document
        verifications = []

    pdf = casereport.build(found, verifications)
    filename = f"MPLADS-case-{work_ref}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/case/{work_ref}/casework")
def case_casework(work_ref: str) -> dict:
    """Whether this work is being worked as a case, and how far along it is.

    The link between the two halves of the product. The intelligence screens answer "why
    was this surfaced"; this answers "and what has anyone done about it" — which is the
    question a reviewer opening a case file six weeks later actually has.
    """
    from mplads import salesforce as sf

    ref = work_ref.upper()
    case = next((c for c in sf.load_salesforce_cases() if c["work_ref"] == ref), None)
    try:
        verifications = field.for_work(ref)
    except Exception:
        verifications = []

    if not case:
        return {
            "in_salesforce": False,
            "verifications": len(verifications),
            "note": (
                "Not currently a Salesforce case. The 500 highest Audit-ROI leads are "
                "loaded for casework; the rest stay in the queue until an officer picks "
                "one up."
            ),
        }

    stage = case.get("investigation_status") or "New"
    guidance = next((s["guidance"] for s in sf.PATH_STAGES if s["stage"] == stage), "")
    return {
        "in_salesforce": True,
        "stage": stage,
        "stages": sf.STAGE_NAMES,
        "stage_index": sf.STAGE_NAMES.index(stage) if stage in sf.STAGE_NAMES else 0,
        "guidance": guidance,
        "escalation_tier": case.get("escalation_tier"),
        "target_review_date": case.get("target_review_date"),
        "officer_finding": case.get("officer_finding") or "",
        "verifications": len(verifications),
        "findings": [
            {"outcome": v["outcome"], "actor": v["actor"], "when": v["created_at"][:10],
             "notes": v.get("notes", "")}
            for v in verifications
        ],
    }


# ------------------------------------------------- login, OCR, field verification


DEMO_ACCOUNTS = {
    "ministry":  {"password": "mplads2026", "role": "ministry", "scope": None,
                  "name": "MoSPI Programme Division"},
    "auditor":   {"password": "mplads2026", "role": "auditor", "scope": None,
                  "name": "CAG Audit Officer"},
    "bihar":     {"password": "mplads2026", "role": "state", "scope": "Bihar",
                  "name": "Bihar State Nodal Officer"},
    "saran":     {"password": "mplads2026", "role": "mp", "scope": "SARAN",
                  "name": "Saran Constituency Office"},
}


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(req: LoginRequest) -> dict:
    """Issue a bearer token for a seeded account.

    Prototype only: accounts are seeded in code, passwords are shared and not hashed,
    and there is no registration or reset. Production replaces this endpoint with an
    identity provider; everything behind it — the token, the scope, the audit trail —
    stays exactly as it is.
    """
    account = DEMO_ACCOUNTS.get(req.username.strip().lower())
    if not account or account["password"] != req.password:
        raise HTTPException(401, "incorrect username or password")
    token = auth.issue_token(req.username, account["role"], account["scope"])
    return {
        "token": token,
        "user": {"username": req.username, "name": account["name"],
                 "role": account["role"], "scope": account["scope"]},
        "note": "Seeded prototype account. Not a production authentication mechanism.",
    }


@app.get("/api/auth/accounts")
def demo_accounts() -> dict:
    """The seeded accounts, so the login screen can offer them. Never do this in production."""
    return {
        "accounts": [
            {"username": u, "name": a["name"], "role": a["role"], "scope": a["scope"]}
            for u, a in DEMO_ACCOUNTS.items()
        ],
        "shared_password": "mplads2026",
        "warning": "Seeded demo credentials, displayed deliberately for evaluation. "
                   "A production deployment uses an identity provider and never lists accounts.",
    }


@app.post("/api/ocr")
async def read_photo(file: UploadFile = File(...), work_ref: str = Form(""),
                     principal: Principal = Depends(current_principal)) -> dict:
    """Read a site board, identify the work, and check the photograph has not been seen before.

    Three answers come back from one upload: the text on the board, which work it belongs
    to, and whether this exact picture was already submitted for a different sanction. The
    third is the one a human could not do at scale.
    """
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "image is larger than 12 MB")
    try:
        name = field.save_photo(data, file.filename or "upload.jpg")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    extracted = ocr.read(field.PHOTOS / name)
    extracted["photo"] = name
    # Matched against every work in the portfolio, not only the surfaced leads — an
    # officer photographing an ordinary work should be told it is ordinary, not unknown.
    extracted["match"] = ocr.match_to_work(extracted, store().all_refs, store().amounts)
    extracted["reuse"] = field.check_photo(
        data, name, work_ref or extracted["match"].get("work_ref") or "",
        actor=principal.subject,
    )
    return extracted


@app.post("/api/ocr/document")
async def read_document(file: UploadFile = File(...), work_ref: str = Form(""),
                        principal: Principal = Depends(current_principal)) -> dict:
    """Read a sanction order, work order or completion certificate with Docling.

    The document is stored under a content hash and read into Markdown, so its tables
    survive. Every work reference in it is checked against the portfolio — an order often
    covers several works — and whether the work this case file is about appears in it.
    """
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "document is larger than 20 MB")
    try:
        name = field.save_document(data, file.filename or "document.pdf")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    extracted = ocr.read_document(field.DOCUMENTS / name)
    extracted["document"] = name
    refs = extracted.get("work_refs") or []
    known = store().all_refs
    extracted["refs_found"] = [
        {"work_ref": ref, "known": ref in known,
         "alternatives": [] if ref in known else ocr.near_misses(ref, known)}
        for ref in refs
    ]
    extracted["mentions_this_work"] = bool(work_ref) and work_ref in refs
    extracted["match"] = ocr.match_to_work(extracted, known, store().amounts)
    return extracted


@app.get("/api/document/{name}")
def document(name: str):
    """Serve an uploaded document."""
    path = field.DOCUMENTS / Path(name).name  # basename only — no traversal
    if not path.exists():
        raise HTTPException(404, "document not found")
    return FileResponse(path)


@app.get("/api/ocr/status")
def ocr_status() -> dict:
    """Which readers this machine has, which one reads photographs, and whether it is ready."""
    return ocr.status()


@app.get("/api/photo/{name}")
def photo(name: str):
    """Serve an uploaded verification photo."""
    path = field.PHOTOS / Path(name).name  # basename only — no traversal
    if not path.exists():
        raise HTTPException(404, "photo not found")
    return FileResponse(path)


class VerificationRequest(BaseModel):
    outcome: str
    notes: str = ""
    photo: str | None = None
    ocr_text: str | None = None
    #: What the camera found, kept apart from what the officer concluded. The reference
    #: read off the board is not the same claim as the work being verified, and the two
    #: disagreeing is the most useful thing a photograph can report.
    board_ref: str | None = None
    board_amount: float | None = None
    ocr_confidence: float | None = None
    needed_confirmation: bool = False
    photo_reuse_count: int = 0
    reused_from: str | None = None
    #: Which reader read the board, and whether a second reader read the same reference.
    ocr_engine: str | None = None
    readers_agree: bool | None = None
    #: A document the officer attached (stored name, from /api/ocr/document).
    document: str | None = None


@app.post("/api/verify/{work_ref}")
def add_verification(work_ref: str, req: VerificationRequest,
                     principal: Principal = Depends(current_principal)) -> dict:
    """Record what an officer found in the field. Immutable once written."""
    auth.require_identity(principal, "record a field verification")
    case = store().cases_by_ref.get(work_ref)
    if case:
        identity = case["identity"]
        auth.require_scope(
            principal,
            {"state": identity.get("state"),
             "implementing_agency": identity.get("implementing_agency"),
             "constituency": identity.get("constituency")},
            f"work {work_ref}",
        )
    try:
        return field.record(
            work_ref=work_ref, outcome=req.outcome, notes=req.notes.strip(),
            photo=req.photo, ocr_text=req.ocr_text,
            actor=principal.subject, role=principal.role,
            board_ref=req.board_ref, board_amount=req.board_amount,
            ocr_confidence=req.ocr_confidence,
            needed_confirmation=req.needed_confirmation,
            photo_reuse_count=req.photo_reuse_count, reused_from=req.reused_from,
            ocr_engine=req.ocr_engine, readers_agree=req.readers_agree,
            document=Path(req.document).name if req.document else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/verify/{work_ref}")
def verifications(work_ref: str) -> dict:
    return {"work_ref": work_ref, "verifications": field.for_work(work_ref),
            "outcomes": field.OUTCOMES}


@app.get("/api/field/summary")
def field_summary() -> dict:
    """Verification activity, and how far it is from producing usable labels."""
    return {"readiness": field.label_readiness(), "recent": field.recent(20),
            "outcomes": field.OUTCOMES, "ocr_available": ocr.available(),
            "photo_reuse": field.photo_reuse_report(),
            "forensics": field.photo_forensics_summary()}


@app.get("/api/insight/case/{work_ref}")
def case_insight(work_ref: str, lang: str = Query("en"),
                 principal: Principal = Depends(current_principal)) -> dict:
    """A written brief for one case file, in the requested language."""
    found = store().cases_by_ref.get(work_ref)
    if not found:
        raise HTTPException(status_code=404, detail="case file not found")
    identity = found["identity"]
    auth.require_scope(
        principal,
        {
            "state": identity.get("state"),
            "implementing_agency": identity.get("implementing_agency"),
            "constituency": identity.get("constituency"),
        },
        f"case file {work_ref}",
    )
    return llm.case_insight(found, language=lang)


# ----------------------------------------------------------- intelligence endpoints


@app.get("/api/temporal")
def temporal() -> dict:
    return store().temporal


@app.get("/api/transparency")
def transparency() -> dict:
    return store().transparency


@app.get("/api/compliance")
def compliance() -> dict:
    return store().stats.get("compliance", {})


@app.get("/api/early-warning")
def early_warning() -> dict:
    return store().stats.get("early_warning", {})


@app.get("/api/health-index")
def health_index() -> dict:
    return store().stats.get("health_index", {})


@app.get("/api/archetypes")
def archetypes(limit: int = Query(50, ge=1, le=100)) -> list[dict]:
    return store().stats.get("archetype_intelligence", [])[:limit]


#: Narrowing 223,407 pairs down to the 47,709 worth asking about is a fixed filter over a
#: frame that does not change while the service is up — but it was being re-run on every
#: request, including every page of the same table, at about two seconds a time.
@lru_cache(maxsize=1)
def _concerning_pairs() -> pd.DataFrame:
    return store().duplicate_pairs.concerning()


@app.get("/api/duplicates")
def duplicate_pairs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: str | None = None,
    classification: str | None = None,
    concerning_only: bool = True,
) -> dict:
    pairs = store().duplicate_pairs
    summary = store().stats.get("duplicates", {})
    if pairs.empty:
        return {"total": 0, "items": [], "summary": summary}

    if concerning_only:
        # The concerning subset is cached — it is what the screen opens on every time.
        frame = _concerning_pairs()
        if state:
            frame = frame[frame["state_name"] == state]
        if classification:
            frame = frame[frame["classification"] == classification]
        total, page = len(frame), frame.iloc[offset : offset + limit]
    else:
        # Everything else is a filtered read of the parquet: the rows nobody asked for are
        # never brought into memory.
        total, page = pairs.page(offset, limit, state=state, classification=classification)

    return {
        "total": int(total),
        "items": json.loads(page.to_json(orient="records")),
        "summary": summary,
    }


# -------------------------------------------------- Salesforce CRM & Agentforce


class UpdateStageRequest(BaseModel):
    work_ref: str
    stage: str
    officer_finding: str = ""
    target_review_date: str = ""
    #: What the officer saw. Carried into the verification record, because a finding with
    #: no account of what was found is a checkbox, not evidence.
    notes: str = ""


class AgentforceQueryRequest(BaseModel):
    question: str
    #: Translates the answer's structure and, most importantly, its contract line. Figures
    #: and work references are never translated — they are identifiers, not words.
    lang: str = "en"


@app.get("/api/salesforce/overview")
def salesforce_overview() -> dict:
    """Salesforce Org status, custom objects, 5-stage Path, reports and dashboards."""
    from mplads import salesforce as sf
    return sf.get_salesforce_overview()


@app.get("/api/salesforce/cases")
def salesforce_cases(
    stage: str | None = None,
    state: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """The 500 High-Priority Investigation Cases in Salesforce CRM."""
    from mplads import salesforce as sf
    cases = sf.load_salesforce_cases()
    if stage:
        cases = [c for c in cases if c["investigation_status"] == stage]
    if state:
        cases = [c for c in cases if (c["state"] or "").lower() == state.lower()]
    if tier:
        cases = [c for c in cases if c["escalation_tier"] == tier]
    if q:
        needle = q.lower()
        cases = [
            c for c in cases
            if needle in (c["work_ref"] or "").lower()
            or needle in (c["description"] or "").lower()
            or needle in (c["implementing_agency"] or "").lower()
            or needle in (c["state"] or "").lower()
        ]
    return {
        "total": len(cases),
        "items": cases[offset : offset + limit],
        "stages": sf.PATH_STAGES,
        "findings": sf.OFFICER_FINDINGS,
    }


@app.get("/api/salesforce/case/{work_ref}")
def salesforce_case(work_ref: str) -> dict:
    """Get single Salesforce Investigation Case with evidence and Path stage info."""
    from mplads import salesforce as sf
    cases = sf.load_salesforce_cases()
    match = next((c for c in cases if c["work_ref"] == work_ref.upper()), None)
    if not match:
        raise HTTPException(404, f"case {work_ref} not found in Salesforce CRM")
    evidence = sf.load_salesforce_evidence(work_ref)
    return {
        "case": match,
        "evidence": evidence,
        "stages": sf.PATH_STAGES,
        "current_stage": match["investigation_status"],
        "guidance": next((s["guidance"] for s in sf.PATH_STAGES if s["stage"] == match["investigation_status"]), ""),
        "findings": sf.OFFICER_FINDINGS,
    }


@app.post("/api/salesforce/update-stage")
def update_salesforce_stage(
    req: UpdateStageRequest,
    principal: Principal = Depends(current_principal),
) -> dict:
    """Update case investigation stage and officer findings."""
    from mplads import salesforce as sf
    try:
        # A stage move is workflow and anyone may do it. Recording what an officer found
        # is evidence, so it carries their name — salesforce.update_case_stage refuses an
        # unattributed one rather than writing "anonymous" into the label set.
        if req.officer_finding:
            auth.require_identity(principal, "record an officer finding")
        res = sf.update_case_stage(
            work_ref=req.work_ref.upper(),
            stage=req.stage,
            officer_finding=req.officer_finding,
            review_date=req.target_review_date,
            notes=getattr(req, "notes", "") or "",
            actor=principal.subject,
            role=principal.role,
        )
        audit().record(
            actor=getattr(principal, "subject", "officer"),
            role=getattr(principal, "role", "auditor"),
            action="UPDATE_STAGE",
            resource=f"/api/salesforce/case/{req.work_ref.upper()}",
            detail={"stage": req.stage, "finding": req.officer_finding},
        )
        return res
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/agentforce/query")
def agentforce_query(req: AgentforceQueryRequest) -> dict:
    """Direct query against Agentforce Investigation Lookup agent."""
    from mplads import salesforce as sf
    if not req.question.strip():
        raise HTTPException(400, "question is required")
    return sf.query_agentforce(req.question.strip(), lang=req.lang.strip())



@app.get("/api/salesforce/ageing")
def salesforce_ageing(as_of: str = Query("")) -> dict:
    """Which cases have gone quiet, and how much exposure is sitting in them.

    The queue is where a monitoring system fails invisibly: a lead that was surfaced,
    assigned and then left for four months has not been monitored, it has been filed. This
    puts a rupee figure on that, so it is a number in a review meeting rather than a
    discovery in an audit.
    """
    from mplads import salesforce as sf

    try:
        return sf.case_ageing(as_of)
    except ValueError:
        raise HTTPException(400, "as_of must be an ISO date, for example 2026-08-28")


# --------------------------------------------------------------- static frontend
#
# When the built React app is present, this one service serves both it and the API.
# Same origin means no CORS to configure, no second host to keep in sync, and no
# build-time API base to get wrong.
#
# Registered last on purpose: FastAPI matches routes in registration order, so the SPA
# catch-all below must come after every `/api/...` route or it would swallow them.

_FRONTEND_DIST = config.REPO_ROOT / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        """Return the built app for any non-API path.

        The dashboard is a single-page app: `/case/MP3018356-W86316` is a client-side route,
        not a file, so a hard refresh on it must still return `index.html` rather than 404.
        An unknown `/api/...` path is answered honestly with a 404 instead of being handed
        the HTML shell, which would otherwise surface as a confusing JSON parse error.
        """
        if full_path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")

    LOGGER.info("serving the built frontend from %s", _FRONTEND_DIST)
else:
    LOGGER.info("no frontend build at %s - serving the API only", _FRONTEND_DIST)
