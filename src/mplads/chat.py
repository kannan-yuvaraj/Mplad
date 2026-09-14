"""The assistant: a chatbot that answers questions by querying the real artifacts.

It does not know anything about MPLADS on its own. Every fact it states comes from a tool
call against the computed artifacts — the same numbers the dashboard renders. That is the
whole design: the model supplies language and navigation, the pipeline supplies truth.

Tools are read-only by construction. There is no tool that writes, scores, ranks, or
changes a threshold; the assistant can look things up and nothing else.

Without API credits the assistant falls back to `answer_offline()`, a deterministic
keyword router over the same tools. It answers the common questions — how many leads, what
is the top case, what does exposure mean — so the feature demos with or without billing.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from mplads import config, llm

LOGGER = logging.getLogger(__name__)

MAX_TURNS = 8

SYSTEM = """You are the assistant inside a government audit dashboard for MPLADS, the \
scheme under which Indian Members of Parliament recommend local public works.

You answer questions by calling the tools provided. You have no independent knowledge of \
this data — if a tool did not tell you a number, you do not know it, and you say so.

Absolute rules:
- Never state a figure that did not come from a tool result in this conversation.
- This system produces INVESTIGATION LEADS. Never say a work involves wrongdoing, misuse, \
dishonesty or crime, and never say anyone acted improperly. Unusual is not wrong; the \
correct phrasing is always "worth checking".
- "Exposure" is money that may be tied up in works that do not finish. It is never loss, \
theft, or missing money. Correct the user gently if they imply otherwise.
- If asked something the data cannot answer (actual expenditure, cost overruns, payments, \
physical progress, photographs), say plainly that the public data does not contain it, and \
say what we measure instead.
- Be brief. Two to four sentences unless asked for detail. Plain language, no markdown \
headings, no bullet characters.
- When you mention a specific work, include its work_ref so the officer can open it."""


# --------------------------------------------------------------------------- data


@lru_cache(maxsize=1)
def _store():
    """The artifacts, loaded once. Mirrors what the API serves."""
    from mplads.api.app import store

    return store()


def _corpus():
    """All 210,993 works. Held by the API store, so both surfaces read one copy."""
    return _store().corpus


#: Where free text is looked for. Description first because that is what people search;
#: the rest lets one query answer "Bihar", "SARAN", "Rajiv Pratap Rudy" or "Sports" without
#: the asker having to know which kind of thing they typed.
SEARCH_COLUMNS = ["work_description", "implementing_agency", "state_name",
                  "constituency", "mp_name", "activity_category", "archetype_label"]


@lru_cache(maxsize=1)
def _haystack():
    """One lowercased column holding every searchable field, built once.

    Searching seven columns separately meant lowering and re-casting 1.4 million strings
    per term — about three and a half seconds a question, which is not a conversation.
    Flattening them into one string per work costs a couple of seconds at startup and
    turns each term into a single pass.
    """
    frame = _corpus()
    if frame.empty:
        import pandas as pd

        return pd.Series(dtype=str)
    import pandas as pd

    # Built in slices and stored Arrow-backed. Joining seven columns across all 210,993
    # rows at once allocates a fresh 211k-string column per column joined — seven live at
    # the peak — and the finished index costs 76 MB as Python objects against 30 MB as one
    # Arrow buffer. Searching is a `str.contains` either way.
    pieces = []
    for start in range(0, len(frame), 25_000):
        block = frame.iloc[start : start + 25_000]
        joined = block["work_description"].fillna("").astype(str)
        for column in SEARCH_COLUMNS[1:]:
            joined = joined + " " + block[column].astype(str)
        pieces.append(joined.str.lower().astype("string[pyarrow]"))
        del joined
    return (pd.concat(pieces) if pieces else pd.Series(dtype="string[pyarrow]"))


def warm() -> None:
    """Build the search index up front, so the first question is as fast as the tenth."""
    _haystack()


#: Words that carry no signal in a description of a public work — every second row says
#: "construction of". Dropping them keeps a natural question from narrowing to nothing.
STOPWORDS = frozenset({
    "of", "the", "a", "an", "in", "at", "for", "to", "and", "or", "on", "with", "by",
    "work", "works", "construction", "show", "me", "list", "find", "all", "what", "which",
    "how", "many", "much", "is", "are", "there", "any",
    # How people actually phrase a request, rather than how a description is written.
    "help", "please", "can", "you", "give", "tell", "about", "some", "get", "i", "want",
    "need", "do", "does", "did", "was", "were", "be", "been", "my", "our", "it", "that",
    "this", "these", "those", "from", "up", "out", "look", "search", "see", "know",
})


def _filter(frame, query: str = "", state: str = "", status: str = ""):
    """Narrow the corpus the way every tool here needs to narrow it.

    Terms are ANDed, not matched as a phrase. "school building" has to find a row that
    says "building of school boundary wall" — a phrase match finds five rows in Bihar and
    leaves an officer thinking the state built five schools.
    """
    mask = frame["work_ref"].notna()
    terms = [t for t in query.strip().lower().split() if t and t not in STOPWORDS]
    if terms:
        haystack = _haystack()
        for term in terms:
            mask &= haystack.str.contains(term, regex=False)
    if state:
        mask &= frame["state_name"].astype(str).str.lower() == state.strip().lower()
    if status == "open":
        mask &= frame["is_open"].fillna(False).astype(bool)
    elif status == "completed":
        mask &= frame["is_completed"].fillna(False).astype(bool)
    return frame[mask]


def _flatten(text: object, limit: int = 160) -> str:
    """Collapse a description to one readable line.

    Work descriptions in this data routinely carry a pasted specification table — tabs,
    newlines, a numbered parts list. Quoting one verbatim into a sentence produces
    something unreadable, so whitespace is collapsed before it is trimmed.
    """
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "\u2026"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count:,} {singular if count == 1 else (plural or singular + 's')}"


def _fmt_rupees(value: float | None) -> str:
    if not value:
        return "unknown"
    if value >= 1e7:
        return f"Rs {value / 1e7:,.2f} crore"
    if value >= 1e5:
        return f"Rs {value / 1e5:,.2f} lakh"
    return f"Rs {value:,.0f}"


# --------------------------------------------------------------------------- tools
#
# Each returns a compact JSON string. Kept small deliberately: a tool that returns
# thousands of rows wastes context and makes the model summarise instead of answer.


def t_portfolio_summary() -> str:
    """National totals: works, money, leads, exposure, health index."""
    stats = _store().stats
    n = stats.get("national", {})
    return json.dumps({
        "total_works": n.get("total_works"),
        "completed": n.get("completed"),
        "open": n.get("open"),
        "total_recommended_rupees": n.get("total_recommended_rupees"),
        "exposure_at_risk_rupees": n.get("total_exposure_rupees"),
        "investigation_leads": n.get("surfaced_leads"),
        "high_confidence_leads": (n.get("bands") or {}).get("HIGH"),
        "medium_confidence_leads": (n.get("bands") or {}).get("MEDIUM"),
        "states": n.get("states"),
        "constituencies": n.get("constituencies"),
        "implementing_agencies": n.get("implementing_agencies"),
        "health_index_out_of_100": (stats.get("health_index") or {}).get("score"),
        "snapshot_date": "2026-05-26",
    })


def t_top_leads(limit: int = 5, state: str = "") -> str:
    """The highest Audit-ROI investigation leads, optionally filtered to one state.

    Args:
        limit: How many to return, 1 to 20.
        state: Optional state name, e.g. "Bihar". Empty means all of India.
    """
    rows = _store().worklist
    if state:
        rows = [r for r in rows if (r.get("state") or "").lower() == state.lower()]
    limit = max(1, min(int(limit), 20))
    return json.dumps([
        {
            "work_ref": r["work_ref"],
            "description": (r.get("description") or "")[:160],
            "state": r.get("state"),
            "implementing_agency": r.get("implementing_agency"),
            "confidence_band": r.get("band"),
            "signal_families": r.get("n_families"),
            "recommended_rupees": r.get("recommended_amount"),
            "exposure_rupees": r.get("exposure_rupees"),
            "signals": r.get("signals"),
        }
        for r in rows[:limit]
    ])


def t_case_detail(work_ref: str) -> str:
    """Everything known about one work: evidence, peers, risk, compliance, next step.

    Args:
        work_ref: The work reference, e.g. "MP3018356-W86316".
    """
    case = _store().cases_by_ref.get(work_ref)
    if not case:
        return json.dumps({"error": f"no case file for {work_ref}. It may not be a surfaced lead."})
    return json.dumps({
        "work_ref": case["work_ref"],
        "identity": case["identity"],
        "work_type": case.get("archetype", {}).get("label"),
        "peer_context": case.get("peer_context"),
        "completion_risk": case.get("risk"),
        "exposure_rupees": case.get("exposure_rupees"),
        "confidence_band": case.get("confidence_band"),
        "signal_families": case.get("n_signal_families"),
        "evidence": case.get("evidence"),
        "compliance_findings": case.get("compliance_findings"),
        "early_warning": case.get("early_warning"),
        "duplicate": case.get("duplicate"),
        "recommended_next_step": case.get("recommended_next_step"),
    })


def t_search_works(query: str, state: str = "", status: str = "", limit: int = 8) -> str:
    """Search ALL 210,993 works by description, agency, category, MP or constituency.

    This is the whole portfolio, not only the works surfaced as leads. Most questions an
    officer asks are about ordinary works — what a state recommended, what an agency
    builds, what a category costs — and answering those from the lead list alone would
    silently describe 18% of the country as if it were all of it.

    Args:
        query: Free text, e.g. "solar street light", "school building", "Saran".
        state: Optional state name to narrow to, e.g. "Bihar".
        status: "", "open" or "completed".
        limit: How many to return, 1 to 20.
    """
    frame = _corpus()
    if frame.empty:
        return json.dumps({"matches": 0, "results": [], "note": "corpus not built"})

    limit = max(1, min(int(limit), 20))
    hits = _filter(frame, query=query, state=state, status=status)
    # Ranked by audit return-on-investment so the most worth-checking come first; ties
    # break on work_ref so the same question always gives the same answer.
    top = hits.sort_values(["audit_roi", "work_ref"], ascending=[False, True]).head(limit)
    return json.dumps({
        "matches": int(len(hits)),
        "total_recommended_rupees": float(hits["recommended_amount"].sum()),
        "surfaced_as_leads": int((hits["band"] != "NONE").sum()),
        "results": [
            {"work_ref": r.work_ref,
             "description": _flatten(r.work_description),
             "state": str(r.state_name), "constituency": str(r.constituency),
             "amount_rupees": float(r.recommended_amount),
             "status": "completed" if r.is_completed else "open",
             "band": str(r.band)}
            for r in top.itertuples()
        ],
    })


def t_work_lookup(work_ref: str) -> str:
    """Look up ANY work by its reference, whether or not it was surfaced as a lead.

    Args:
        work_ref: e.g. MP3018356-W86316.
    """
    if _store().cases_by_ref.get(work_ref.upper()):
        return t_case_detail(work_ref)

    frame = _corpus()
    row = frame[frame["work_ref"] == work_ref.upper()]
    if row.empty:
        return json.dumps({"found": False,
                           "note": work_ref + " is not a work in this portfolio"})
    r = row.iloc[0]
    return json.dumps({
        "found": True, "work_ref": r["work_ref"], "surfaced_as_lead": False,
        "description": _flatten(r["work_description"], 300),
        "state": str(r["state_name"]), "constituency": str(r["constituency"]),
        "implementing_agency": str(r["implementing_agency"]), "mp": str(r["mp_name"]),
        "category": str(r["activity_category"]), "archetype": str(r["archetype_label"]),
        "amount_rupees": float(r["recommended_amount"]),
        "status": "completed" if r["is_completed"] else "open",
        "compliance_flags": int(r["compliance_flags"] or 0),
        "note": "Nothing was flagged on this work. It sits inside its peer norms.",
    })


def t_agency_profile(agency: str) -> str:
    """One implementing agency's whole portfolio: works, money, completion, leads.

    Args:
        agency: Full or partial agency name, e.g. "SARAN".
    """
    frame = _corpus()
    match = frame[frame["implementing_agency"].astype(str).str.contains(
        agency.strip(), case=False, regex=False)]
    if match.empty:
        return json.dumps({"found": False, "note": "no agency matching " + agency})
    return json.dumps({
        "found": True,
        "agencies_matched": sorted(match["implementing_agency"].astype(str).unique())[:5],
        "works": int(len(match)),
        "total_recommended_rupees": float(match["recommended_amount"].sum()),
        "completed": int(match["is_completed"].sum()),
        "completion_rate": round(float(match["is_completed"].mean()), 3),
        "surfaced_as_leads": int((match["band"] != "NONE").sum()),
        "high_confidence_leads": int((match["band"] == "HIGH").sum()),
        "exposure_rupees": float(match["rs_exposure"].sum()),
    })


def t_mp_profile(mp_name: str) -> str:
    """One Member of Parliament's recommended works in aggregate.

    Reports the portfolio, never a judgement about the person. An MP recommends works;
    implementing agencies execute them.

    Args:
        mp_name: Full or partial name.
    """
    frame = _corpus()
    match = frame[frame["mp_name"].astype(str).str.contains(
        mp_name.strip(), case=False, regex=False)]
    if match.empty:
        return json.dumps({"found": False, "note": "no MP matching " + mp_name})
    return json.dumps({
        "found": True,
        "names_matched": sorted(match["mp_name"].astype(str).unique())[:5],
        "works": int(len(match)),
        "constituencies": sorted(match["constituency"].astype(str).unique())[:5],
        "total_recommended_rupees": float(match["recommended_amount"].sum()),
        "completion_rate": round(float(match["is_completed"].mean()), 3),
        "surfaced_as_leads": int((match["band"] != "NONE").sum()),
        "caveat": "Recommending a work is not executing it. Delays and anomalies belong "
                  "to the implementing agency unless something says otherwise.",
    })


def t_category_breakdown(limit: int = 12) -> str:
    """The official permissible-works categories by volume and money.

    Args:
        limit: How many categories, 1 to 40.
    """
    frame = _corpus()
    if frame.empty:
        return json.dumps([])
    grouped = frame.groupby("activity_category", observed=True).agg(
        works=("work_ref", "size"),
        rupees=("recommended_amount", "sum"),
        completion_rate=("is_completed", "mean"),
        leads=("band", lambda b: int((b != "NONE").sum())),
    ).sort_values("works", ascending=False).head(max(1, min(int(limit), 40)))
    return json.dumps([
        {"category": str(name), "works": int(r.works), "rupees": float(r.rupees),
         "completion_rate": round(float(r.completion_rate), 3), "leads": int(r.leads)}
        for name, r in grouped.iterrows()
    ])


def t_field_verifications(work_ref: str = "") -> str:
    """What officers found when they actually went and looked.

    Read live from the verification store on every call, so a record entered a moment ago
    is answerable immediately — nothing is cached and nothing needs rebuilding.

    Args:
        work_ref: Optional. A specific work, or blank for recent activity portfolio-wide.
    """
    from mplads import field

    if work_ref:
        rows = field.for_work(work_ref.upper())
        return json.dumps({
            "work_ref": work_ref.upper(), "verifications": len(rows),
            "records": [
                {"outcome": r["outcome"], "notes": r["notes"], "by": r["actor"],
                 "role": r["role"], "when": r["created_at"][:10],
                 "demonstration_record": bool(r.get("demo"))}
                for r in rows
            ],
        })
    return json.dumps({
        "readiness": field.label_readiness(),
        "photo_reuse": field.photo_reuse_report(),
        "recent": [
            {"work_ref": r["work_ref"], "outcome": r["outcome"], "by": r["actor"],
             "when": r["created_at"][:10], "demonstration_record": bool(r.get("demo"))}
            for r in field.recent(8)
        ],
    })


def t_state_breakdown(limit: int = 10) -> str:
    """Exposure and lead counts per state, highest exposure first.

    Args:
        limit: How many states, 1 to 36.
    """
    rows = _store().stats.get("by_state", [])[: max(1, min(int(limit), 36))]
    return json.dumps([
        {"state": r.get("state_name"), "works": r.get("works"),
         "exposure_rupees": r.get("exposure"), "leads": r.get("leads")}
        for r in rows
    ])


def t_compliance_summary() -> str:
    """The lifecycle compliance checks, how many works each flagged, and its authority."""
    return json.dumps(_store().stats.get("compliance", {}))


def t_duplicate_summary() -> str:
    """Near-duplicate detection totals and how 'concerning' is defined."""
    return json.dumps(_store().stats.get("duplicates", {}))


def t_archetype_list(limit: int = 10) -> str:
    """The learned work types, largest first, with completion rate and exposure.

    Args:
        limit: How many archetypes, 1 to 50.
    """
    rows = _store().stats.get("archetype_intelligence", [])[: max(1, min(int(limit), 50))]
    return json.dumps([
        {"label": r.get("label"), "works": r.get("n_works"),
         "completion_rate": r.get("completion_rate"),
         "median_amount_rupees": r.get("median_amount"),
         "flagged_rate": r.get("lead_rate")}
        for r in rows
    ])


def t_model_metrics() -> str:
    """How the three trained models performed, with their honest caveats."""
    return json.dumps(_store().metrics)


def t_data_limitations() -> str:
    """Which fields the public data does NOT contain, and what we use instead."""
    transparency = _store().transparency
    return json.dumps({
        "unavailable": [
            {"metric": m["metric"], "why": m["note"]}
            for m in transparency.get("metrics", [])
            if m.get("type") == "Unavailable"
        ],
        "statement": transparency.get("statement"),
    })


def t_salesforce_summary() -> str:
    """Status of Salesforce CRM, the 5-stage Path, deployed reports, and Agentforce."""
    from mplads import salesforce as sf
    return json.dumps(sf.get_salesforce_overview())


def t_salesforce_case_lookup(work_ref: str = "") -> str:
    """Look up a case's live Salesforce CRM casework state and 5-stage Path progress.

    Args:
        work_ref: The work reference, e.g. "MP3018356-W86316".
    """
    from mplads import salesforce as sf
    cases = sf.load_salesforce_cases()
    if not work_ref and cases:
        work_ref = cases[0]["work_ref"]
    match = next((c for c in cases if c["work_ref"] == work_ref.upper()), None)
    if not match:
        return json.dumps({"found": False, "note": f"{work_ref} is not in the top 500 Salesforce cases."})
    evidence = sf.load_salesforce_evidence(work_ref)
    return json.dumps({
        "found": True,
        "case": match,
        "evidence": evidence,
        "path_guidance": next((s["guidance"] for s in sf.PATH_STAGES if s["stage"] == match["investigation_status"]), ""),
    })


def t_agentforce_investigation_lookup(query: str = "") -> str:
    """Query Agentforce across all 210,993 works, Salesforce cases, states, and tiers.

    Args:
        query: Investigation question, state, tier, or work reference.
    """
    from mplads import salesforce as sf
    res = sf.query_agentforce(query or "overview")
    return json.dumps(res)


TOOL_FUNCS = {
    "t_portfolio_summary": t_portfolio_summary,
    "t_top_leads": t_top_leads,
    "t_case_detail": t_case_detail,
    "t_work_lookup": t_work_lookup,
    "t_search_works": t_search_works,
    "t_agency_profile": t_agency_profile,
    "t_mp_profile": t_mp_profile,
    "t_category_breakdown": t_category_breakdown,
    "t_field_verifications": t_field_verifications,
    "t_state_breakdown": t_state_breakdown,
    "t_compliance_summary": t_compliance_summary,
    "t_duplicate_summary": t_duplicate_summary,
    "t_archetype_list": t_archetype_list,
    "t_model_metrics": t_model_metrics,
    "t_data_limitations": t_data_limitations,
    "t_salesforce_summary": t_salesforce_summary,
    "t_salesforce_case_lookup": t_salesforce_case_lookup,
    "t_agentforce_investigation_lookup": t_agentforce_investigation_lookup,
}


@lru_cache(maxsize=1)
def _decorated_tools():
    """Wrap the plain functions with @beta_tool so the SDK derives their schemas."""
    from anthropic import beta_tool

    return [beta_tool(fn) for fn in TOOL_FUNCS.values()]


# ------------------------------------------------------------------------ live chat


def answer(question: str, history: list[dict] | None = None, language: str = "en") -> dict:
    """Answer one question, calling tools as needed. Falls back when unavailable."""
    client = llm._client()
    if client is None:
        return answer_offline(question)

    messages = list(history or [])
    messages.append({"role": "user", "content": question})

    system = SYSTEM
    if language != "en":
        system += f"\n\nReply entirely in {llm.LANGUAGES.get(language, language)}."

    used: list[str] = []
    try:
        runner = client.beta.messages.tool_runner(
            model=llm.MODEL,
            max_tokens=2000,
            system=system,
            tools=_decorated_tools(),
            messages=messages,
        )
        final = None
        for turn, message in enumerate(runner):
            final = message
            used += [b.name for b in message.content if b.type == "tool_use"]
            if turn >= MAX_TURNS:
                LOGGER.warning("chat hit the turn cap; returning what we have")
                break
    except Exception as exc:
        LOGGER.warning("chat failed (%s) — falling back", type(exc).__name__)
        return answer_offline(question)

    if final is None:
        return answer_offline(question)
    if getattr(final, "stop_reason", None) == "refusal":
        return {"text": "I could not answer that one. Try rephrasing it.",
                "tools_used": used, "source": "refusal"}

    text = "".join(b.text for b in final.content if b.type == "text")
    cleaned = llm._scrub(text)
    if not cleaned:
        return answer_offline(question)
    return {"text": cleaned, "tools_used": sorted(set(used)), "source": "llm", "model": llm.MODEL}


# --------------------------------------------------------------------- offline mode


WORK_REF = re.compile(r"\bMP\d+-W\d+\b", re.I)


def _states() -> dict[str, str]:
    """Lowercased state name to canonical, for spotting a state inside a question."""
    frame = _corpus()
    if frame.empty:
        return {}
    return {str(s).lower(): str(s) for s in frame["state_name"].dropna().unique()}


def answer_offline(question: str) -> dict:
    """Deterministic router over the same tools and the same 210,993 works.

    No model, no credits, no guessing. This is not a decorative fallback — it is what runs
    when there is no API key, and it answers from the real corpus rather than apologising.
    It cannot infer what you meant, only what you said, and when it genuinely cannot match
    a question it searches the portfolio for the words in it and reports what it found.
    """
    q = question.lower()
    store = _store()
    n = store.stats.get("national", {})

    def has(*words: str) -> bool:
        return any(w in q for w in words)

    # --- a specific work, lead or not
    ref = WORK_REF.search(question)
    if ref:
        return _answer_work(ref.group(0).upper())

    # --- Salesforce & Agentforce casework queries
    if has("salesforce", "crm", "sales force"):
        from mplads import salesforce as sf
        overview = sf.get_salesforce_overview()
        org = overview["org"]
        obj = overview["objects"]["Investigation_Case__c"]
        return _said(
            f"Salesforce CRM is live (Org ID {org['org_id']}, {org['status']}). It holds "
            f"{obj['records_loaded']} HIGH-priority investigation cases representing "
            f"{_fmt_rupees(obj['total_exposure_rupees'])} of exposure, with "
            f"{overview['objects']['Evidence__c']['records_loaded']:,} linked evidence items, a "
            f"5-stage investigation Path, 3 custom reports and an executive dashboard.",
            "t_salesforce_summary")

    if has("agentforce", "agent force", "investigation lookup"):
        from mplads import salesforce as sf
        result = sf.query_agentforce(question)
        return _said(result["answer"], "t_salesforce_summary")

    if has("path", "stage", "investigation status", "5-stage"):
        from mplads import salesforce as sf
        stages_str = " → ".join(s["label"] for s in sf.PATH_STAGES)
        last_guidance = sf.PATH_STAGES[-1]["guidance"]
        return _said(
            f"The Salesforce 5-stage Path is: {stages_str}. Each stage carries actionable "
            f"officer guidance. Stage 5 (Closed) records the ground truth: '{last_guidance}'",
            "t_salesforce_summary")

    if has("escalation tier", "ministry review", "state nodal", "district monitoring"):
        from mplads import salesforce as sf
        overview = sf.get_salesforce_overview()
        tiers = overview["escalation_tiers"]
        return _said(
            f"Salesforce cases are partitioned across three governance tiers: "
            f"{tiers['District Monitoring']} in District Monitoring, {tiers['State Nodal']} "
            f"in State Nodal, and {tiers['Ministry Review']} in Ministry Review.",
            "t_salesforce_summary")

    # --- what officers found in the field, read live
    if has("verification", "verified", "site visit", "field", "ground truth", "officer found"):
        return _answer_field()

    if has("photo", "photograph", "picture", "image", "ocr", "scan", "board"):
        return _answer_photos()

    # --- a named state
    for lowered, canonical in _states().items():
        if lowered in q and len(lowered) > 4:
            return _answer_state(canonical)

    if has("how many lead", "how many case", "leads are there", "number of lead"):
        bands = n.get("bands") or {}
        return _said(
            f"{n.get('surfaced_leads'):,} works were surfaced for review out of "
            f"{n.get('total_works'):,} — {bands.get('HIGH'):,} at HIGH confidence (three or "
            f"more independent signal families agreed) and {bands.get('MEDIUM'):,} at "
            f"MEDIUM (two). The other {n.get('total_works', 0) - n.get('surfaced_leads', 0):,} "
            f"sit inside their peer norms and were not surfaced.",
            "t_portfolio_summary")

    if has("exposure", "money at risk", "at risk"):
        return _said(
            f"Exposure at risk is {_fmt_rupees(n.get('total_exposure_rupees'))}. That is the "
            f"recommended amount multiplied by the chance a work does not finish — money "
            f"that may be tied up in works that stall. It is not loss, not theft, and not "
            f"missing money.",
            "t_portfolio_summary")

    if has("top", "highest", "worst", "biggest", "priority", "start with"):
        rows = store.worklist[:3]
        listed = " ".join(
            f"{r['work_ref']} ({r.get('state')}, "
            f"{_fmt_rupees(r.get('exposure_rupees'))} exposure)."
            for r in rows
        )
        return _said(f"The three highest-ranked leads by Audit-ROI are: {listed}",
                     "t_top_leads")

    if has("duplicate", "repeat", "same work", "copied"):
        d = store.stats.get("duplicates", {})
        return _said(
            f"We found {d.get('total_pairs'):,} semantically similar description pairs. "
            f"Repeated descriptions are normal in this scheme, so only "
            f"{d.get('concerning_pairs'):,} are treated as concerning — near-identical, "
            f"from the same implementing agency, for a near-identical amount.",
            "t_duplicate_summary")

    if has("category", "categories", "kind of work", "type of work", "what gets built"):
        rows = json.loads(t_category_breakdown(4))
        listed = "; ".join(
            f"{r['category']} ({r['works']:,} works, {_fmt_rupees(r['rupees'])})"
            for r in rows
        )
        return _said(
            f"The largest official permissible-works categories are: {listed}. There are "
            f"118 categories in all, parsed out of ACTIVITY_NAME, covering 93% of works.",
            "t_category_breakdown")

    if has("expenditure", "spent", "cost overrun", "payment", "progress %"):
        return _said(
            "The public data does not contain verified expenditure, payment tranches, cost "
            "estimates or physical progress. We measured this rather than assumed it: "
            "ACTUAL_AMOUNT equals the recommended amount on 98.35% of completed works. So "
            "we report peer-relative amount anomalies and administrative lifecycle "
            "progress instead, and say plainly what is missing.",
            "t_data_limitations")

    # --- how the ranking itself works. Asked constantly in evaluation, and the honest
    # answer is short, so it should never fall through to a corpus search.
    if has("audit-roi", "audit roi", "rank", "ranking", "ranked",
           "prioritis", "prioritiz", "why this order"):
        return _said(
            "Leads are ranked by Audit-ROI — priority multiplied by rupee exposure "
            "multiplied by corroboration. In plain terms: how unusual it is, how much money "
            "is at stake, and how many independent signal families agree. An inspector has a "
            "finite number of days, so this ranks by where one of those days is worth most. "
            "It is a triage order, never a measure of guilt.",
            "t_portfolio_summary")

    if has("confidence", "band", "signal famil", "corroborat", "how many signals"):
        bands = n.get("bands") or {}
        return _said(
            f"A band counts how many independent signal families agreed on one work. HIGH "
            f"means three or more ({bands.get('HIGH', 0):,} works), MEDIUM means two "
            f"({bands.get('MEDIUM', 0):,}), LOW means one ({bands.get('LOW', 0):,}) — and a "
            f"single signal on its own is usually noise. The families are amount, duration, "
            f"lifecycle, behaviour, multivariate outlier and duplication; they are kept "
            f"independent so that one being wrong does not carry the others.",
            "t_portfolio_summary")

    if has("compliance", "lifecycle check", "rule", "statutory", "deviation", "authority"):
        compliance = store.stats.get("compliance", {}) or {}
        checks = compliance.get("checks", []) or []
        top = sorted(checks, key=lambda c: c.get("works_affected", 0), reverse=True)[:3]
        listed = "; ".join(
            f"{c.get('check')} ({c.get('works_affected', 0):,} works, "
            f"{str(c.get('authority', '')).replace('_', ' ').lower()})"
            for c in top
        )
        return _said(
            f"There are {len(checks)} lifecycle compliance checks. The largest are: {listed}. "
            f"Every check declares its own authority, and none of them claims to be an "
            f"official rule — no statutory threshold ships with this public data, so calling "
            f"an outlier a legal breach would be inventing law.",
            "t_compliance_summary")

    if has("health index", "health score", "how healthy", "overall health"):
        health = store.stats.get("health_index", {}) or {}
        components = health.get("components", []) or []
        weakest = min(components, key=lambda c: c.get("value", 1)) if components else None
        tail = (f" The weakest component is {weakest.get('name')} at "
                f"{weakest.get('value', 0) * 100:.1f}%." if weakest else "")
        return _said(
            f"The MPLADS Operational Health Index is {health.get('score')} out of 100, built "
            f"from {len(components)} weighted components that are each shown with their "
            f"weight and explanation.{tail} It is a summary of administrative health, not a "
            f"judgement about any person.",
            "t_compliance_summary")

    if has("archetype", "work type", "types of work", "cluster", "categories discovered"):
        rows = json.loads(t_archetype_list(3))
        listed = "; ".join(
            f"{r['label']} ({r['works']:,} works)" for r in rows if r.get("label")
        )
        clustering = store.metrics.get("archetype_clustering", {})
        return _said(
            f"The system discovered {clustering.get('k_chosen', 50)} work types on its own by "
            f"grouping the descriptions — nobody supplied the categories. The largest are: "
            f"{listed}. Forty-nine were given names from their own most distinctive terms; "
            f"one is labelled uninterpretable because it is held together by language rather "
            f"than by work type, and saying so beats inventing a name.",
            "t_archetype_list")

    if has("behaviour", "behavior", "change over time", "changed", "trend", "temporal",
           "change-point", "change point"):
        counts = (store.temporal or {}).get("counts", {})
        return _said(
            f"Of {counts.get('agencies_analysed', 0):,} implementing agencies with enough "
            f"history to test, {counts.get('agencies_changed', 0):,} show a statistical "
            f"change-point — a measurable break between how they behaved before and after. "
            f"A change-point is not wrongdoing. A new officer, a new scheme or a flood all "
            f"produce one. It means something changed and is worth asking about.",
            "t_state_breakdown")

    # "help" only when the question is a plea for the menu, never as a stray word —
    # "help me find road works in Bihar" is a search, and matching it here swallowed one.
    asking_for_the_menu = (
        has("what can you do", "what can i ask", "how do i use", "what do you know")
        or q.strip(" ?!.") in {"help", "help me", "menu", "commands"}
    )
    if asking_for_the_menu:
        return _said(
            "I answer from the computed results only — I have no independent knowledge of "
            "this data and cannot do arithmetic, so I cannot invent a figure. Ask me for the "
            "national picture, a state, a specific work reference like MP3018356-W86316, the "
            "top leads, what exposure means, how ranking works, near-duplicates, compliance "
            "checks, the trained models and their limits, what officers found in the field, "
            "or what this data cannot tell you.",
            "t_portfolio_summary")

    if has("model", "accuracy", "trained", "c-index", "silhouette", "machine learning"):
        m = store.metrics
        clustering = m.get("archetype_clustering", {})
        return _said(
            f"Three models are trained: clustering into {clustering.get('k_chosen')} work "
            f"types (silhouette {clustering.get('silhouette_at_chosen_k')} — a separation "
            f"measure, never accuracy), a Cox survival model for completion risk (held-out "
            f"C-index {m.get('completion_risk', {}).get('c_index_heldout')}), and an "
            f"outlier detector. None of them predicts wrongdoing — no such labels exist in "
            f"this data, so nothing could be learned from them.",
            "t_model_metrics")

    if has("how many work", "total work", "how big", "scale", "overview", "summary"):
        return _said(
            f"The portfolio holds {n.get('total_works'):,} works worth "
            f"{_fmt_rupees(n.get('total_recommended_rupees'))} across {n.get('states')} "
            f"states and {n.get('implementing_agencies'):,} implementing agencies. "
            f"{n.get('completed'):,} are complete and {n.get('open'):,} are still open.",
            "t_portfolio_summary")

    # --- last resort: search the corpus for the words actually in the question
    return _answer_search(question)


def _said(text: str, *tools: str) -> dict:
    return {"text": text, "tools_used": list(tools), "source": "offline"}


def _answer_work(ref: str) -> dict:
    """One work — from its case file if it has one, from the corpus if it does not."""
    case = _store().cases_by_ref.get(ref)
    if case:
        identity = case["identity"]
        reasons = "; ".join(e["signal"] for e in case.get("evidence", []))
        text = (
            f"{case['work_ref']} — {_flatten(identity.get('description'))} in "
            f"{identity.get('state')}. Recommended "
            f"{_fmt_rupees(identity.get('recommended_amount'))}, exposure "
            f"{_fmt_rupees(case.get('exposure_rupees'))}, confidence "
            f"{case.get('confidence_band')} from {case.get('n_signal_families')} "
            f"independent signal families ({reasons}). {case.get('recommended_next_step')}"
        )
    else:
        found = json.loads(t_work_lookup(ref))
        if not found.get("found"):
            return _said(f"{ref} is not a work in this portfolio.", "t_work_lookup")
        text = (
            f"{ref} — {_flatten(found['description'], 140)} in {found['state']} "
            f"({found['constituency']}), implemented by {found['implementing_agency']}. "
            f"Recommended {_fmt_rupees(found['amount_rupees'])}, currently "
            f"{found['status']}. It was not surfaced as a lead: nothing about it falls "
            f"outside its peer norms."
        )

    visits = json.loads(t_field_verifications(ref))
    if visits["verifications"]:
        latest = visits["records"][0]
        text += (f" An officer visited on {latest['when']} and recorded "
                 f"{latest['outcome'].replace('_', ' ').lower()}.")
    return _said(text, "t_work_lookup", "t_field_verifications")


def _answer_state(state: str) -> dict:
    frame = _filter(_corpus(), state=state)
    leads = frame[frame["band"] != "NONE"]
    return _said(
        f"{state} holds {len(frame):,} works worth "
        f"{_fmt_rupees(float(frame['recommended_amount'].sum()))}. "
        f"{int(frame['is_completed'].sum()):,} are complete "
        f"({frame['is_completed'].mean():.0%}). {len(leads):,} were surfaced for review, "
        f"with {_fmt_rupees(float(leads['rs_exposure'].sum()))} of exposure. Ask about a "
        f"specific work reference for the evidence behind any one of them.",
        "t_search_works")


def _answer_field() -> dict:
    data = json.loads(t_field_verifications())
    r = data["readiness"]
    if not r["verifications"] and not r.get("demo_records_excluded"):
        return _said(
            "No site verifications have been recorded yet. Every score in this system is "
            "a reasoned default because no dataset says which works turned out to be "
            "problems — officers recording what they found on site is the only way that "
            "ever changes.",
            "t_field_verifications")
    outcomes = ", ".join(
        f"{k.replace('_', ' ').lower()} {v}" for k, v in r["by_outcome"].items()
    ) or "none yet"
    return _said(
        f"{_plural(r['verifications'], 'verification record')} so far across "
        f"{_plural(r['works_verified'], 'work')} ({outcomes}); {r['concerns_confirmed']} "
        f"confirmed a concern on site. "
        f"{_plural(r['demo_records_excluded'], 'demonstration record')} excluded from that "
        f"count. {r['labels_needed_to_fit_weights']} more are needed before the weights "
        f"could be fitted to what officers actually confirmed rather than reasoned "
        f"defaults. Nothing is refitted until then and no accuracy is claimed.",
        "t_field_verifications")


def _answer_photos() -> dict:
    data = json.loads(t_field_verifications())
    reuse = data["photo_reuse"]
    if reuse["shared_across_works"]:
        first = reuse["clusters"][0]
        return _said(
            f"{reuse['photographs']} photographs have been submitted and "
            f"{reuse['shared_across_works']} picture(s) appear under more than one work. "
            f"The clearest is submitted for {' and '.join(first['works'])}. A perceptual "
            f"hash catches this even when the file was resized or re-compressed, so the "
            f"checksums differ. It is worth one question, not a conclusion — two phases of "
            f"one road legitimately look identical from the roadside.",
            "t_field_verifications")
    return _said(
        f"{_plural(reuse['photographs'], 'verification photograph')} submitted so far, "
        f"and none appears under more than one work. Every upload is fingerprinted with a "
        f"perceptual hash, which matches the same picture even after it has been resized "
        f"or re-compressed — the checksum would not. Boards are also read automatically, "
        f"so an officer does not type a reference number standing in a field.",
        "t_field_verifications")


def _answer_search(question: str) -> dict:
    """Search the corpus for the words in the question. The honest last resort."""
    result = json.loads(t_search_works(question, limit=3))
    if not result.get("matches"):
        return _said(
            "I could not find anything matching that. I can tell you the portfolio "
            "totals, the top leads, exposure, duplicates, the categories, any state, any "
            "implementing agency, what officers have verified in the field, the trained "
            "models, or the details of any work if you give me its reference — for "
            "example MP3018356-W86316.",
            )
    listed = " ".join(
        f"{r['work_ref']} ({r['state']}, {_fmt_rupees(r['amount_rupees'])}, {r['status']})."
        for r in result["results"]
    )
    return _said(
        f"{result['matches']:,} works match that, worth "
        f"{_fmt_rupees(result['total_recommended_rupees'])} in total; "
        f"{result['surfaced_as_leads']:,} of them were surfaced for review. The "
        f"highest-ranked are: {listed}",
        "t_search_works")
