"""The live sync cycle.

**The portal offers no push and no incremental read.** There is no webhook, no
change feed, no `modified_since` parameter, no ETag and no Last-Modified header
on any of the endpoints — all verified. So "live" here means *polled*, and the
honest statement of latency is "bounded by the poll interval", never "real
time". `ingestion/live/README.md` says so in the same words.

What makes polling cheap enough to run continuously is that the portal will tell
us **where** something changed for ~450 bytes:

    getTilesData(scope) -> counts AND rupees-to-the-paisa for that scope

So one cycle is:

    144 aggregate calls  (36 states x 2 houses x 2 tenures)   ~3 minutes
        -> compare each against the stored fingerprint
        -> for ONLY the scopes that moved, fetch their 5 tile reports
        -> diff every work and payment, write the change feed

On a quiet hour that is 144 small requests and nothing else. When a district
authority sanctions a batch of works, exactly that state's scope moves and only
it is re-read.

**The limitation, stated rather than buried.** A change that leaves both the
count *and* the total rupees identical is invisible to the fingerprint — a work
cancelled and another added for exactly the same amount in the same scope, or a
description corrected. `sync_full()` exists for that reason and is meant to run
on a slow cadence (nightly). Aggregate polling is the fast path, not the only
path.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from ingestion import api, config
from ingestion.api import Scope
from ingestion.client import PortalClient, PortalError
from ingestion.live.store import LiveStore, SyncCounters
from ingestion.normalizer.normalize import _official_category, _parse_date
from ingestion.storage.manifest import sha256_bytes, utc_now_iso

log = logging.getLogger(__name__)

#: Tiles whose value we fingerprint. `Current Tenure` is metadata, not a measure.
FINGERPRINT_TILES = (
    "Works Recommended", "Works Sanctioned", "Works Completed",
    "Expenditure on Completed and On-going Works as on Date",
    "Allocated Limit for Hon'ble MPs", "Amount consented for Calamity",
)

#: A scope that has not moved in this many consecutive checks is polled less
#: often. Retired Rajya Sabha tenures do not change; spending the same attention
#: on them as on an active Lok Sabha state wastes requests that a live state
#: could have had.
COLD_AFTER_UNCHANGED = 12
COLD_POLL_EVERY = 6


def fingerprint(tiles: dict[str, Any]) -> str:
    """A stable digest of a scope's published totals."""
    material = {k: tiles.get(k) for k in FINGERPRINT_TILES if k in tiles}
    return sha256_bytes(json.dumps(material, sort_keys=True,
                                   ensure_ascii=False).encode("utf-8"))


def iter_scopes() -> Iterator[tuple[Scope, dict[str, Any]]]:
    """Every (state, house, tenure) scope, from the enumerated reference data."""
    ref = config.RAW_API / "reference"
    states_file = ref / "states.json"
    if not states_file.exists():
        raise RuntimeError("run `ingestion.cli enumerate` before starting the live sync")

    states = json.loads(states_file.read_text(encoding="utf-8"))
    tenures: dict[int, list[dict[str, Any]]] = {}
    for house in config.HOUSES:
        path = ref / f"tenures_house{house}.json"
        if path.exists():
            tenures[house] = json.loads(path.read_text(encoding="utf-8"))

    for state in states:
        sid = int(state["STATE_ID"])
        for house, house_tenures in tenures.items():
            for tenure in house_tenures:
                yield (
                    Scope(state_id=sid, house=house, tenure_id=int(tenure["ID"])),
                    {"STATE_ID": sid, "STATE_NAME": state["STATE_NAME"],
                     "house": house, "tenure_id": int(tenure["ID"]),
                     "tenure": tenure["CAPTION"]},
                )


def _work_row(raw: dict[str, Any], labels: dict[str, Any],
              mp_index: dict[str, int]) -> dict[str, Any] | None:
    """One portal work row, shaped for the live store."""
    wid = raw.get("WORK_RECOMMENDATION_DTL_ID")
    if wid is None:
        return None

    mp_name = raw.get("MP_NAME")
    mp_id = mp_index.get((mp_name or "").strip().lower())
    activity = raw.get("ACTIVITY_NAME")

    return {
        # Without an mp_id the key falls back to the scope, which still keys
        # uniquely because a work id is unique within a state/house/tenure.
        "work_ref": f"MP{mp_id}-W{wid}" if mp_id else f"S{labels['STATE_ID']}-W{wid}",
        "work_recommendation_dtl_id": int(wid),
        "mp_id": mp_id,
        "mp_name": mp_name,
        "state_id": labels["STATE_ID"],
        "state_name": raw.get("STATE_NAME") or labels["STATE_NAME"],
        "constituency_id": raw.get("CONSTITUENCY_ID"),
        "constituency": raw.get("CONSTITUENCY"),
        "house": labels["house"],
        "tenure_id": labels["tenure_id"],
        "tenure": raw.get("TENURE") or labels["tenure"],
        "ida_name": raw.get("IDA_NAME"),
        "work_category": raw.get("WORK_CATEGORY"),
        "activity_name": activity,
        "official_category": _official_category(activity),
        "work_description": raw.get("WORK_DESCRIPTION"),
        "letter_no": raw.get("LETTER_NO"),
        "work_stage": raw.get("WORK_STAGE"),
        "stage_flag": raw.get("FLAG"),
        "recommendation_date": str(_parse_date(raw.get("RECOMMENDATION_DATE")) or "") or None,
        "sanction_date": str(_parse_date(raw.get("SANCTION_DATE")) or "") or None,
        "actual_end_date": str(_parse_date(raw.get("ACTUAL_END_DATE")) or "") or None,
        "recommended_amount": raw.get("RECOMMENDED_AMOUNT"),
        "sanction_amount": raw.get("SANCTION_AMOUNT"),
        "actual_amount": raw.get("ACTUAL_AMOUNT"),
        "attach_parent_id": raw.get("ATTACH_ID"),
        "portal_work_id": str(raw["WORK_ID"]) if raw.get("WORK_ID") is not None else None,
    }


def _payment_row(raw: dict[str, Any], labels: dict[str, Any],
                 work_refs: dict[int, str]) -> dict[str, Any] | None:
    wid = raw.get("WORK_RECOMMENDATION_DTL_ID")
    if wid is None:
        return None
    return {
        "work_recommendation_dtl_id": int(wid),
        "work_ref": work_refs.get(int(wid)),
        "vendor_id": raw.get("VENDOR_ID"),
        "vendor_name": raw.get("VENDOR_NAME"),
        "ia_name": raw.get("IA_NAME"),
        "ida_name": raw.get("IDA_NAME"),
        "expenditure_date": str(_parse_date(raw.get("EXPENDITURE_DATE")) or "") or None,
        "fund_disbursed_amount": raw.get("FUND_DISBURSED_AMT"),
        "work_status": raw.get("WORK_STATUS"),
        "state_name": raw.get("STATE_NAME") or labels["STATE_NAME"],
        "mp_name": raw.get("MP_NAME"),
    }


def _mp_index() -> dict[str, int]:
    """MP name -> mp_id, so live rows carry the same `work_ref` the rest of the
    project uses. The portal's work rows give a name but never an id."""
    index: dict[str, int] = {}
    mps_dir = config.RAW_API / "reference" / "mps"
    if not mps_dir.exists():
        return index
    for path in mps_dir.glob("*.json"):
        try:
            for row in json.loads(path.read_text(encoding="utf-8")):
                name = str(row.get("CAPTION", "")).strip().lower()
                if name:
                    index.setdefault(name, int(row["ID"]))
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            continue
    return index


def _refresh_scope(client: PortalClient, store: LiveStore, scope: Scope,
                   labels: dict[str, Any], run_id: int, counters: SyncCounters,
                   mp_index: dict[str, int]) -> None:
    """Re-read one scope's work and payment rows and diff them into the store."""
    combo = scope.to_combo()
    works: list[dict[str, Any]] = []

    for key in ("Works Recommended", "Works Sanctioned", "Works Completed"):
        try:
            report = api.get_tile_report(client, scope, key)
            counters.requests_made += 1
        except (PortalError, api.PortalShapeError) as exc:
            counters.errors += 1
            counters.error_detail.append(f"{combo}/{key}: {exc}")
            continue
        for raw in report.rows:
            row = _work_row(raw, labels, mp_index)
            if row:
                works.append(row)

    # Later stages carry fields earlier ones do not, so merge per work rather
    # than letting the completed row's missing recommendation_date blank it.
    merged: dict[str, dict[str, Any]] = {}
    for row in works:
        target = merged.setdefault(row["work_ref"], {})
        for field_name, value in row.items():
            if value not in (None, ""):
                target[field_name] = value
            target.setdefault(field_name, value)

    store.upsert_works(list(merged.values()), run_id=run_id, combo=combo, counters=counters)

    work_refs = {r["work_recommendation_dtl_id"]: r["work_ref"] for r in merged.values()}
    try:
        report = api.get_tile_report(
            client, scope, "Expenditure on Completed and On-going Works as on Date")
        counters.requests_made += 1
        payments = [p for p in (_payment_row(r, labels, work_refs) for r in report.rows) if p]
        store.upsert_payments(payments, run_id=run_id, combo=combo, counters=counters)
    except (PortalError, api.PortalShapeError) as exc:
        counters.errors += 1
        counters.error_detail.append(f"{combo}/expenditure: {exc}")


def sync_once(*, mode: str = "incremental", store: LiveStore | None = None,
              limit_scopes: int | None = None) -> dict[str, Any]:
    """One sync cycle.

    `incremental` polls every scope's aggregate and refreshes only what moved.
    `full` skips the fingerprint check and refreshes everything — the nightly
    safety net for changes that leave the totals identical.
    """
    store = store or LiveStore()
    counters = SyncCounters()
    run_id = store.start_run(mode)
    mp_index = _mp_index()
    ok = True

    scopes = list(iter_scopes())
    if limit_scopes is not None:
        scopes = scopes[:limit_scopes]

    try:
        with PortalClient() as client:
            for index, (scope, labels) in enumerate(scopes):
                combo = scope.to_combo()
                watermark = store.get_watermark(combo)

                # Cold scopes are polled less often, not never.
                if (mode == "incremental" and watermark is not None
                        and watermark["consecutive_unchanged"] >= COLD_AFTER_UNCHANGED
                        and (watermark["check_count"] + index) % COLD_POLL_EVERY):
                    continue

                if mode == "incremental":
                    try:
                        tiles, _ = api.get_tiles(client, scope)
                        counters.requests_made += 1
                        counters.scopes_polled += 1
                    except PortalError as exc:
                        counters.errors += 1
                        counters.error_detail.append(f"{combo}/tiles: {exc}")
                        continue

                    digest = fingerprint(tiles)
                    changed = watermark is None or watermark["fingerprint"] != digest
                    store.record_check(combo=combo, labels=labels, fingerprint=digest,
                                       tiles=tiles, changed=changed)
                    if not changed:
                        continue
                    counters.scopes_changed += 1
                    log.info("scope %s moved — refreshing", combo)
                else:
                    counters.scopes_polled += 1
                    counters.scopes_changed += 1

                _refresh_scope(client, store, scope, labels, run_id, counters, mp_index)

    except Exception as exc:  # a cycle must never take the scheduler down
        ok = False
        counters.errors += 1
        counters.error_detail.append(f"cycle aborted: {type(exc).__name__}: {exc}")
        log.exception("sync cycle failed")

    store.finish_run(run_id, counters, ok and counters.errors == 0)

    result = {
        "run_id": run_id,
        "mode": mode,
        "finished_at": utc_now_iso(),
        "ok": ok and counters.errors == 0,
        **{k: v for k, v in vars(counters).items() if k != "error_detail"},
        "error_detail": counters.error_detail[:20],
    }
    log.info("sync %s: polled=%d changed=%d works+%d~%d payments+%d~%d requests=%d errors=%d",
             mode, counters.scopes_polled, counters.scopes_changed,
             counters.works_appeared, counters.works_changed,
             counters.payments_appeared, counters.payments_changed,
             counters.requests_made, counters.errors)
    return result


def sync_full(**kwargs: Any) -> dict[str, Any]:
    """Refresh every scope regardless of its fingerprint."""
    return sync_once(mode="full", **kwargs)
