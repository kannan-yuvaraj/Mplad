"""Live-feed endpoints: freshness, the change feed, and live figures.

Mounted by `app.py`. Everything here is **additive** — no existing route changes
behaviour, and if the live database has never been written these endpoints
report that plainly instead of failing or, worse, returning zeros that look
like real measurements.

The distinction this module exists to keep visible:

- `data/artifacts/works_scored.parquet` is the **scored snapshot**. The models,
  the leads, the audit plan and every screen are built on it. It changes when
  the pipeline is re-run.
- `data/portal/live/mplads_live.sqlite` is the **live mirror** of the portal,
  updated every sync cycle.

They are different ages, on purpose, and the UI must never imply otherwise —
`/api/live/status` returns both ages so a screen can show the gap rather than
average it away.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import re

from fastapi import APIRouter, HTTPException, Query

LOGGER = logging.getLogger(__name__)


def _ensure_ingestion_importable() -> None:
    """Put the repository root on `sys.path` so `ingestion` can be imported.

    `ingestion/` sits beside `src/`, not inside it, so it is only importable when
    the process happens to have been started from the repository root. Run
    uvicorn with `--app-dir src` — as the launch configuration does — and every
    endpoint here silently degrades to "the live feed is not initialised", which
    is indistinguishable from a machine that genuinely never ran a sync.

    Deriving the root from `mplads.config` rather than from the current working
    directory means it holds however the server was started.
    """
    import sys

    try:
        from mplads import config as _config
        root = str(_config.REPO_ROOT)
    except Exception:  # config unavailable: nothing useful to add
        return
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_ingestion_importable()

router = APIRouter(prefix="/api/live", tags=["live"])

#: `<parent>.<child>`, digits only. The id goes straight into a portal request,
#: so it is validated here rather than trusted from the URL.
_ATTACH_ID = re.compile(r"^\d+\.\d+$")

#: Imported lazily so the API still starts when the ingestion package or the
#: live database is absent — a deployment without the feed must degrade to the
#: snapshot, not fail to boot.
_UNAVAILABLE = {
    "available": False,
    "reason": "the live feed has not been initialised on this machine",
    "how_to_start": "python -m ingestion.cli live-sync   (one cycle)  |  "
                    "python -m ingestion.cli live-run    (the service)",
}


def _store() -> Any | None:
    try:
        from ingestion.live.store import LiveStore
    except ImportError as exc:
        LOGGER.debug("ingestion package unavailable: %s", exc)
        return None
    try:
        from ingestion.live.store import DB_PATH
        if not Path(DB_PATH).exists():
            return None
        return LiveStore()
    except Exception as exc:  # a broken live DB must not take the API down
        LOGGER.warning("live store unavailable: %s", exc)
        return None


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(iso)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - stamp).total_seconds(), 1)
    except ValueError:
        return None


@router.get("/status")
def live_status() -> dict[str, Any]:
    """Is the feed alive, how fresh is it, and how far has it drifted from the
    scored snapshot the rest of the site is built on?"""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)

    status = store.status()

    try:
        from ingestion.live.service import heartbeat
        beat = heartbeat()
    except Exception:
        beat = {"running": False, "reason": "heartbeat unavailable"}

    last_sync = status.get("last_sync") or {}
    finished = last_sync.get("finished_at")

    # The snapshot's age, so a screen can show the two side by side.
    snapshot_age = None
    try:
        from mplads import config as mconfig
        scored = Path(mconfig.ARTIFACTS) / "works_scored.parquet"
        if scored.exists():
            snapshot_age = round(
                (datetime.now(timezone.utc).timestamp() - scored.stat().st_mtime), 1)
    except Exception:
        pass

    return {
        "available": True,
        "service_running": bool(beat.get("running")),
        "heartbeat": beat,
        "last_sync_finished_at": finished,
        "seconds_since_last_sync": _age_seconds(finished),
        "oldest_scope_checked_at": status.get("oldest_scope_checked_at"),
        "seconds_since_oldest_scope_check": _age_seconds(
            status.get("oldest_scope_checked_at")),
        "counts": status.get("counts"),
        "changes_last_24h": status.get("changes_last_24h"),
        "last_sync": last_sync,
        "scored_snapshot_age_seconds": snapshot_age,
        "note": (
            "The live mirror and the scored snapshot are different ages by design. "
            "Leads, risk bands and the audit plan come from the snapshot and only "
            "move when the pipeline is re-run; this feed reflects the portal as of "
            "the last sync. Do not present one figure as the other."
        ),
        "latency_contract": (
            "The portal offers no push, webhook or modified-since read, so freshness "
            "is bounded by the poll interval, not real time."
        ),
    }


@router.get("/changes")
def live_changes(
    limit: int = Query(50, ge=1, le=500),
    entity: str | None = Query(None, pattern="^(work|payment)$"),
    field: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """The change feed: what actually moved on the portal, most recent first."""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)

    rows = store.recent_changes(limit=limit, entity=entity, field_name=field)
    return {
        "available": True,
        "count": len(rows),
        "filters": {"entity": entity, "field": field, "limit": limit},
        "changes": rows,
        "note": ("Each row is one field moving on the portal between two syncs. "
                 "A change is an observation, not a finding — nothing here is an "
                 "assessment of the work or the agency."),
    }


@router.get("/scopes")
def live_scopes() -> dict[str, Any]:
    """Per-scope freshness. Shows which parts of the country are being watched
    closely and which have gone quiet — including the cold ones, so a scope that
    silently stopped being polled cannot hide."""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)

    rows = [dict(r) for r in store.all_watermarks()]
    for row in rows:
        row.pop("tiles_json", None)
        row["seconds_since_check"] = _age_seconds(row.get("last_checked_at"))
    return {
        "available": True,
        "scopes_tracked": len(rows),
        "scopes": rows,
        "note": ("A scope unchanged for many consecutive checks is polled less "
                 "often, not dropped. `consecutive_unchanged` shows why."),
    }


@router.get("/work/{work_ref}")
def live_work(work_ref: str) -> dict[str, Any]:
    """One work as the portal currently has it, with its full change history."""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)

    with store.connect() as conn:
        row = conn.execute("SELECT * FROM work WHERE work_ref=?", (work_ref,)).fetchone()
        if row is None:
            return {
                "available": True,
                "found": False,
                "work_ref": work_ref,
                "reason": ("not in the live mirror. Either the portal does not carry "
                           "it, or its scope has not been synced yet — check "
                           "/api/live/scopes rather than assuming it does not exist."),
            }
        payments = [dict(p) for p in conn.execute(
            "SELECT * FROM payment WHERE work_recommendation_dtl_id=? "
            "ORDER BY expenditure_date",
            (row["work_recommendation_dtl_id"],)).fetchall()]
        history = [dict(c) for c in conn.execute(
            "SELECT * FROM change_log WHERE entity='work' AND entity_id=? "
            "ORDER BY id DESC LIMIT 200", (work_ref,)).fetchall()]

    return {
        "available": True,
        "found": True,
        "work": dict(row),
        "payments": payments,
        "total_disbursed": sum(p.get("fund_disbursed_amount") or 0 for p in payments),
        "change_history": history,
    }


# --------------------------------------------------------------------------
# Evidence: indexed by fingerprint, served on demand
# --------------------------------------------------------------------------

@router.get("/evidence/coverage")
def evidence_coverage() -> dict[str, Any]:
    """How much of the national evidence set has been fingerprinted."""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)
    try:
        from ingestion.live.evidence import coverage
        return {"available": True, **coverage(store)}
    except Exception as exc:
        LOGGER.warning("evidence coverage unavailable: %s", exc)
        return {"available": False, "reason": str(exc)}


@router.get("/evidence/reuse")
def evidence_reuse(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """The same picture indexed under two different works.

    A question for a human, never a finding: two phases of one road legitimately
    look identical from the roadside.
    """
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)
    try:
        from ingestion.live.evidence import reuse_report
        rows = reuse_report(store, max_rows=limit)
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "count": len(rows),
        "groups": rows,
        "note": ("Detected from perceptual hashes, so a resized or re-compressed copy "
                 "still matches. Nothing here is an assessment of a work or an agency."),
    }


@router.get("/evidence/{work_ref}")
def evidence_for_work(work_ref: str) -> dict[str, Any]:
    """What files the portal holds for a work — metadata only, no bytes."""
    store = _store()
    if store is None:
        return dict(_UNAVAILABLE)
    try:
        from ingestion.live.evidence import ensure_schema
        ensure_schema(store)
        with store.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM evidence WHERE work_ref=? ORDER BY kind, file_name",
                (work_ref,)).fetchall()]
    except Exception as exc:
        return {"available": False, "reason": str(exc)}

    for row in rows:
        row["fetch_url"] = f"/api/live/evidence/file/{row['attach_id']}"
    return {
        "available": True,
        "work_ref": work_ref,
        "files": rows,
        "note": ("Fingerprints are stored; the files are not. `fetch_url` pulls one "
                 "from the portal at the moment someone asks for it."),
    }


@router.get("/evidence/file/{attach_id}")
def evidence_file(attach_id: str):
    """Stream one attachment straight from the portal.

    This is the half of the argument that makes discarding the bytes tenable: an
    officer opening a case file gets the real photograph, fetched now, without
    this system ever having held ~306 GB. The cost is a live dependency on the
    portal — if it is down, the file is unavailable, and the response says so
    rather than serving a stale copy it does not have.
    """
    from fastapi.responses import Response

    try:
        from ingestion.client import PortalClient
        from ingestion.live.evidence import fetch_attachment
    except ImportError:
        raise HTTPException(503, "the ingestion package is not installed here")

    if not _ATTACH_ID.match(attach_id):
        raise HTTPException(400, "malformed attachment id")

    with PortalClient() as client:
        payload, error = fetch_attachment(client, attach_id)
    if payload is None:
        raise HTTPException(502, f"the portal did not return this file: {error}")

    from ingestion.storage.attachments import sniff

    media = sniff(payload) or "application/octet-stream"
    if media.startswith("application/zip"):
        media = "application/octet-stream"
    return Response(
        content=payload,
        media_type=media,
        headers={
            "Cache-Control": "private, max-age=600",
            "X-MPLADS-Source": "fetched live from mplads.mospi.gov.in; not stored here",
        },
    )


# --------------------------------------------------------------------------
# Vendor concentration — who gets paid, and how narrowly
# --------------------------------------------------------------------------

#: The report reads every payment row, so it is built once and reused. The live
#: feed moves on a poll interval measured in minutes; recomputing per request
#: would spend seconds to change nothing.
_VENDOR_CACHE: dict[str, Any] = {}


def _vendor_report() -> dict[str, Any] | None:
    store = _store()
    if store is None:
        return None
    try:
        from mplads.intelligence import vendors
    except ImportError:
        return None

    with store.connect() as conn:
        stamp = conn.execute(
            "SELECT COUNT(*) n, COALESCE(MAX(last_seen_at),'') t FROM payment").fetchone()
        key = f"{stamp['n']}:{stamp['t']}"
        if _VENDOR_CACHE.get("key") == key:
            return _VENDOR_CACHE["report"]
        rows = [dict(r) for r in conn.execute(
            "SELECT ida_name, ia_name, state_name, vendor_id, vendor_name, "
            "fund_disbursed_amount FROM payment").fetchall()]

    report = vendors.concentration_report(rows)
    _VENDOR_CACHE.update(key=key, report=report)
    return report


@router.get("/vendors")
def vendor_concentration(
    limit: int = Query(40, ge=1, le=200),
    band: str | None = Query(None, pattern="^(CONCENTRATED|MODERATE|SPREAD)$"),
) -> dict[str, Any]:
    """How narrowly each district authority spreads its money across vendors.

    Answers the question a public-money auditor always asks and which the CSV
    snapshot could not: *is one district paying the same few firms for
    everything?* The vendor only exists on the live feed.
    """
    report = _vendor_report()
    if report is None:
        return dict(_UNAVAILABLE)

    rows = report["authorities"]
    if band:
        rows = [r for r in rows if r.get("band") == band]

    return {
        "available": True,
        "grouped_by": report["grouped_by"],
        "count": len(rows),
        "authorities": rows[:limit],
        "distribution": report["distribution"],
        "coverage": report["coverage"],
        "contract": report["contract"],
        "benchmark_note": report["benchmark_note"],
    }


@router.get("/vendors/{authority}")
def vendor_concentration_for(authority: str) -> dict[str, Any]:
    """One authority's vendor profile, placed in the national spread."""
    report = _vendor_report()
    if report is None:
        return dict(_UNAVAILABLE)

    from mplads.intelligence import vendors

    row = vendors.for_authority(report, authority)
    if row is None:
        return {
            "available": True,
            "found": False,
            "authority": authority,
            "reason": ("no payments for this authority in the live feed yet. "
                       "Check /api/live/vendors coverage before reading that as "
                       "an absence of payments."),
        }
    return {"available": True, "found": True, **row}
