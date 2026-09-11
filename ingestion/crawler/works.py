"""Phase 8 step 2 — the work-grain crawl.

**Scope narrowing is the pagination mechanism.** `getTilesReportData` takes no
page or offset parameter: the server returns every row for the scope in one
response and the dashboard chunks it in the browser. National scope times out;
state scope returns in well under a second. So the crawl unit is

    (state, house, tenure, tile_key)

which is 36 x 2 x ~2 x 5 = roughly 720 requests for the entire national
work-level dataset, each one preserved raw.

Because the unit is a whole state, "page 1 vs page 2 contain different records"
does not apply. The equivalent proof is that two different scopes return
disjoint work-id sets, which `verify_scope_disjointness` demonstrates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from ingestion import api, config
from ingestion.api import Scope
from ingestion.client import PortalClient, PortalError
from ingestion.crawler.checkpoint import Checkpoint
from ingestion.storage.manifest import RawStore

log = logging.getLogger(__name__)


def _reference_path(*parts: str) -> Path:
    return config.RAW_API.joinpath("reference", *parts)


def load_reference() -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """Read the states and tenures written by `enumerate`."""
    states_file = _reference_path("states.json")
    if not states_file.exists():
        raise RuntimeError("run `ingestion.cli enumerate` before `works`")
    states = json.loads(states_file.read_text(encoding="utf-8"))

    tenures: dict[int, list[dict[str, Any]]] = {}
    for house in config.HOUSES:
        path = _reference_path(f"tenures_house{house}.json")
        if path.exists():
            tenures[house] = json.loads(path.read_text(encoding="utf-8"))
    return states, tenures


def iter_scopes(
    states: list[dict[str, Any]],
    tenures: dict[int, list[dict[str, Any]]],
    *,
    house: int | None = None,
    only_state: int | None = None,
) -> Iterator[tuple[Scope, dict[str, Any]]]:
    """Every (state, house, tenure) crawl unit, with its human labels."""
    for state in states:
        sid = int(state["STATE_ID"])
        if only_state is not None and sid != only_state:
            continue
        for h, house_tenures in tenures.items():
            if house is not None and h != house:
                continue
            for tenure in house_tenures:
                tid = int(tenure["ID"])
                yield (
                    Scope(state_id=sid, constituency_id=0, mp_id=0, house=h, tenure_id=tid),
                    {"STATE_NAME": state["STATE_NAME"], "STATE_ID": sid,
                     "house": h, "tenure_id": tid, "tenure": tenure["CAPTION"]},
                )


def run_work_crawl(
    *,
    house: int | None = None,
    only_state: int | None = None,
    limit_scopes: int | None = None,
) -> dict[str, Any]:
    """Crawl work-grain rows for every scope. Resumable at scope-key granularity."""
    states, tenures = load_reference()
    store = RawStore()
    ckpt = Checkpoint.load("works")

    scopes = list(iter_scopes(states, tenures, house=house, only_state=only_state))
    if limit_scopes is not None:
        scopes = scopes[:limit_scopes]

    discovered: set[str] = set()
    rows_written = 0
    scopes_done = 0

    with PortalClient() as client:
        for scope, labels in scopes:
            for key in config.TILE_KEYS:
                unit = f"{scope.slug()}|{key}"
                if ckpt.done(unit):
                    continue
                try:
                    report = api.get_tile_report(client, scope, key)
                except (PortalError, api.PortalShapeError) as exc:
                    log.error("scope %s key %r failed: %s", scope.to_combo(), key, exc)
                    ckpt.fail(unit, url=f"{config.REST_DASHBOARD}/getTilesReportData",
                              error=str(exc), identifier=scope.to_combo(),
                              http_status=getattr(exc, "status", None),
                              retry_count=client.retry_count)
                    continue

                store.write(
                    payload=report.raw.content,
                    destination=config.RAW_API / "works" / scope.slug()
                    / f"{_key_slug(key)}.json",
                    source_url=report.raw.url,
                    request_body=report.raw.request_body,
                    artefact_kind="api",
                    http_status=report.raw.status_code,
                    content_type=report.raw.content_type,
                    identifiers={"combo": scope.to_combo(), "key": key, **labels},
                    note=f"rows={len(report.rows)} grand_total={report.grand_total} "
                         f"(server's trailing Total_Amt row separated, not counted as a work)",
                )
                rows_written += len(report.rows)
                for row in report.rows:
                    wid = row.get("WORK_RECOMMENDATION_DTL_ID")
                    if wid is not None:
                        discovered.add(str(wid))
                ckpt.mark(unit)
                log.info("%s | %-55s rows=%d", scope.to_combo(), key, len(report.rows))
            scopes_done += 1

    ckpt.close()

    summary = {
        "scopes_planned": len(scopes),
        "scopes_processed": scopes_done,
        "units_completed": len(ckpt.completed),
        "rows_written_this_run": rows_written,
        "distinct_works_this_run": len(discovered),
        "failures": len(ckpt.failures),
        "failure_detail": ckpt.failures,
        "requests_made": None,
    }
    store.write_json(obj=summary, destination=config.REPORT_ROOT / "work_crawl_summary.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return summary


def _key_slug(key: str) -> str:
    return key.replace(" ", "_").replace("/", "_").replace("'", "")[:60]


def verify_scope_disjointness(scope_a: Scope, scope_b: Scope) -> dict[str, Any]:
    """Phase 16 proof that scope narrowing really partitions the data.

    Fetches Works Recommended for two scopes and reports the overlap. Two
    different states must share no work id; if they do, the scoping is not a
    partition and the crawl plan is wrong.
    """
    with PortalClient() as client:
        a = api.get_tile_report(client, scope_a, "Works Recommended")
        b = api.get_tile_report(client, scope_b, "Works Recommended")

    ids_a = {str(r["WORK_RECOMMENDATION_DTL_ID"]) for r in a.rows
             if "WORK_RECOMMENDATION_DTL_ID" in r}
    ids_b = {str(r["WORK_RECOMMENDATION_DTL_ID"]) for r in b.rows
             if "WORK_RECOMMENDATION_DTL_ID" in r}
    overlap = ids_a & ids_b

    return {
        "scope_a": scope_a.to_combo(), "rows_a": len(a.rows), "distinct_a": len(ids_a),
        "scope_b": scope_b.to_combo(), "rows_b": len(b.rows), "distinct_b": len(ids_b),
        "overlap": len(overlap),
        "overlap_sample": sorted(overlap)[:10],
        "disjoint": not overlap,
    }
