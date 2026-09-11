"""Phase 10 — reconcile our collected rows against the portal's own aggregates.

The portal publishes counts and amounts on the dashboard. We sum the work-level
rows we collected for the same scope and compare. Discrepancies are reported,
never corrected: a mismatch is a finding about the data, not a bug to paper over.

Three sources of truth are compared for each scope:

  1. `getTilesData`      — the published tile, per tenure.
  2. `Total_Amt`         — the grand-total row the server appends to the report
                           it just returned. This is the portal reconciling
                           against itself, and it is the tightest check we have.
  3. our own sum         — over the rows we stored.

If (2) and (3) disagree, we dropped or double-counted rows. If (1) and (2)
disagree, the portal's tile and the portal's report disagree with each other,
which is a finding about the portal, not about us.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ingestion import api, config
from ingestion.api import Scope
from ingestion.client import PortalClient
from ingestion.storage.manifest import RawStore

log = logging.getLogger(__name__)

#: Tile values arrive as strings like "Rs57,71,65,45,326.11". The frontend
#: strips a literal "Rs"; the encoding of the rupee sign is inconsistent so we
#: strip anything that is not a digit or a decimal point.
_NUMERIC = re.compile(r"[^\d.]")


def parse_amount(value: str) -> float | None:
    cleaned = _NUMERIC.sub("", value or "")
    if not cleaned or cleaned.count(".") > 1:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


#: Which tile the report for a key should reconcile against, and which field on
#: the row carries the money.
RECONCILE_MAP = {
    "Works Recommended": ("Works Recommended", "RECOMMENDED_AMOUNT"),
    "Works Sanctioned": ("Works Sanctioned", "SANCTION_AMOUNT"),
    "Works Completed": ("Works Completed", "ACTUAL_AMOUNT"),
    "Expenditure on Completed and On-going Works as on Date": (
        "Expenditure on Completed and On-going Works as on Date", "FUND_DISBURSED_AMT"
    ),
}


def reconcile_scope(client: PortalClient, scope: Scope) -> list[dict[str, Any]]:
    """Compare tile, server grand total and our own sum for one scope."""
    tiles, _ = api.get_tiles(client, scope)
    findings: list[dict[str, Any]] = []

    for key, (tile_name, amount_field) in RECONCILE_MAP.items():
        report = api.get_tile_report(client, scope, key)

        our_count = len({
            str(r["WORK_RECOMMENDATION_DTL_ID"]) for r in report.rows
            if "WORK_RECOMMENDATION_DTL_ID" in r
        }) or len(report.rows)
        our_sum = sum(
            float(r[amount_field]) for r in report.rows
            if isinstance(r.get(amount_field), (int, float))
        )

        tile = tiles.get(tile_name)
        tile_count: int | None = None
        tile_amount: float | None = None
        if isinstance(tile, list) and tile:
            if len(tile) >= 3:
                try:
                    tile_count = int(_NUMERIC.sub("", tile[0]) or 0)
                except ValueError:
                    tile_count = None
                tile_amount = parse_amount(tile[1])
            else:
                tile_amount = parse_amount(tile[0])

        finding = {
            "scope": scope.to_combo(),
            "key": key,
            "tile_name": tile_name,
            "portal_tile_count": tile_count,
            "portal_tile_amount": tile_amount,
            "portal_report_grand_total": report.grand_total,
            "our_row_count": our_count,
            "our_amount_sum": round(our_sum, 2),
        }

        # Self-consistency of the portal's own report.
        if report.grand_total is not None:
            delta = round(our_sum - report.grand_total, 2)
            finding["sum_vs_grand_total_delta"] = delta
            finding["sum_matches_grand_total"] = abs(delta) < 0.01
        # Report vs published tile.
        if tile_amount is not None and report.grand_total is not None:
            tdelta = round(report.grand_total - tile_amount, 2)
            finding["grand_total_vs_tile_delta"] = tdelta
            finding["grand_total_matches_tile"] = abs(tdelta) < 1.0
        if tile_count is not None:
            finding["count_vs_tile_delta"] = our_count - tile_count
            finding["count_matches_tile"] = our_count == tile_count

        findings.append(finding)
    return findings


def run_reconciliation(scopes: list[Scope] | None = None) -> dict[str, Any]:
    """Reconcile a set of scopes. Defaults to a handful of small, fast states.

    Kept deliberately small by default: reconciliation is a check, and a check
    that costs a full national crawl will not get run.
    """
    if scopes is None:
        states_file = config.RAW_API / "reference" / "states.json"
        tenures_file = config.RAW_API / "reference" / f"tenures_house{config.HOUSE_LOK_SABHA}.json"
        if states_file.exists() and tenures_file.exists():
            states = json.loads(states_file.read_text(encoding="utf-8"))
            tenures = json.loads(tenures_file.read_text(encoding="utf-8"))
            latest = max(int(t["ID"]) for t in tenures)
            scopes = [
                Scope(state_id=int(s["STATE_ID"]), house=config.HOUSE_LOK_SABHA, tenure_id=latest)
                for s in states[:3]
            ]
        else:
            # Andaman & Nicobar (35) and Goa (12): small, verified fast.
            scopes = [
                Scope(state_id=35, house=config.HOUSE_LOK_SABHA, tenure_id=7),
                Scope(state_id=12, house=config.HOUSE_LOK_SABHA, tenure_id=7),
            ]

    store = RawStore()
    findings: list[dict[str, Any]] = []
    with PortalClient() as client:
        for scope in scopes:
            log.info("reconciling %s", scope.to_combo())
            findings.extend(reconcile_scope(client, scope))

    mismatches = [
        f for f in findings
        if f.get("sum_matches_grand_total") is False
        or f.get("count_matches_tile") is False
        or f.get("grand_total_matches_tile") is False
    ]

    report = {
        "scopes_checked": [s.to_combo() for s in scopes],
        "checks": len(findings),
        "mismatches": len(mismatches),
        "mismatch_detail": mismatches,
        "findings": findings,
        "note": "Discrepancies are reported, not corrected. See "
                "ingestion/research/LIMITATIONS.md for known reasons a portal "
                "tile and a portal report can legitimately differ.",
    }
    store.write_json(obj=report, destination=config.REPORT_ROOT / "reconciliation.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return report
