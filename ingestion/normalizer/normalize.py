"""Phase 4 — raw preserved responses to normalized tables.

Reads only from `raw/api/`, never from the network. The raw store is the source
of truth; this module is re-runnable and produces nothing that cannot be
regenerated from the preserved responses.

Provenance (Phase 14) is carried in-band: every normalized row keeps
`source_stored_path` and `source_sha256`, so any field on any row can be traced
to the exact response body it came from and that body re-read from disk.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from ingestion import config
from ingestion.storage.manifest import RawStore, sha256_bytes

log = logging.getLogger(__name__)

#: `ACTIVITY_NAME` is a composite: `WS/MP<code>/<FY>/<serial>-<official category>`.
#: Splitting it yields an interpretable category axis. Same parse as the main
#: pipeline uses; kept here so the ingestion module has no import dependency on
#: `src/mplads`.
ACTIVITY_PATTERN = re.compile(r"^WS/MP\d+/[\d-]+/\d+-(?P<category>.+)$")

DATE_FORMATS = ("%d-%b-%Y",)


def _parse_date(value: Any) -> Any:
    if not value or not isinstance(value, str):
        return None
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(value, format=fmt).date()
        except (ValueError, TypeError):
            continue
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _official_category(activity_name: Any) -> str | None:
    if not isinstance(activity_name, str):
        return None
    match = ACTIVITY_PATTERN.match(activity_name)
    return match.group("category").strip() if match else None


def iter_stored_reports() -> Iterator[tuple[Path, str, str, list[dict[str, Any]], dict[str, Any]]]:
    """(path, sha256, envelope, rows, scope_labels) for every stored work response."""
    root = config.RAW_API / "works"
    if not root.exists():
        return
    for path in sorted(root.rglob("*.json")):
        payload = path.read_bytes()
        digest = sha256_bytes(payload)
        try:
            body = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning("skipping unparseable %s: %s", path, exc)
            continue
        scope = _scope_from_path(path)
        for envelope, value in body.items():
            rows = json.loads(value) if isinstance(value, str) else value
            if not isinstance(rows, list):
                continue
            # Drop the server's trailing grand-total row — it is not a work.
            rows = [r for r in rows if isinstance(r, dict) and set(r) != {"Total_Amt"}]
            yield path, digest, envelope, rows, scope


def _scope_from_path(path: Path) -> dict[str, Any]:
    """Recover the scope from the directory name written by the crawler."""
    match = re.match(r"s(\d+)_c(\d+)_m(\d+)_h(\d+)_t(\w+)", path.parent.name)
    if not match:
        return {}
    return {
        "state_id": int(match.group(1)),
        "constituency_id": int(match.group(2)) or None,
        "mp_id_scope": int(match.group(3)) or None,
        "house": int(match.group(4)),
        "tenure_id": None if match.group(5) == "any" else int(match.group(5)),
    }


def run_normalize() -> dict[str, Any]:
    """Build the normalized tables and write them as parquet."""
    config.ensure_dirs()
    store = RawStore()

    works: dict[tuple[Any, Any], dict[str, Any]] = {}
    payments: list[dict[str, Any]] = []
    allocations: list[dict[str, Any]] = []

    for path, digest, envelope, rows, scope in iter_stored_reports():
        provenance = {"source_stored_path": str(path), "source_sha256": digest}

        for row in rows:
            if envelope == "Total Expenditure":
                payments.append({
                    "work_recommendation_dtl_id": row.get("WORK_RECOMMENDATION_DTL_ID"),
                    "vendor_id": row.get("VENDOR_ID"),
                    "vendor_name": row.get("VENDOR_NAME"),
                    "ia_name": row.get("IA_NAME"),
                    "ida_name": row.get("IDA_NAME"),
                    "expenditure_date": _parse_date(row.get("EXPENDITURE_DATE")),
                    "fund_disbursed_amount": row.get("FUND_DISBURSED_AMT"),
                    "work_status": row.get("WORK_STATUS"),
                    "portal_work_id": row.get("WORK_ID"),
                    "mp_name": row.get("MP_NAME"),
                    "state_name": row.get("STATE_NAME"),
                    "constituency": row.get("CONSTITUENCY"),
                    **scope, **provenance,
                })
                continue

            if envelope == "Allocated Limit":
                allocations.append({
                    "mp_name": row.get("MP_NAME"),
                    "state_name": row.get("STATE_NAME"),
                    "constituency": row.get("CONSTITUENCY"),
                    "house_name": row.get("HOUSE_NAME"),
                    "tenure": row.get("TENURE"),
                    "allocated_amount": row.get("ALLOCATED_AMT"),
                    **scope, **provenance,
                })
                continue

            wid = row.get("WORK_RECOMMENDATION_DTL_ID")
            if wid is None:
                continue
            mp_id = scope.get("mp_id_scope")
            key = (wid, mp_id)

            record = works.setdefault(key, {
                "work_recommendation_dtl_id": wid,
                "mp_id": mp_id,
                **scope, **provenance,
            })

            # Each tile key contributes the fields it carries. Later stages
            # overwrite earlier ones only where they actually have a value, so a
            # completed row cannot blank out a recommendation date.
            for src, dst, transform in (
                ("MP_NAME", "mp_name", None),
                ("STATE_NAME", "state_name", None),
                ("CONSTITUENCY", "constituency", None),
                ("CONSTITUENCY_ID", "constituency_id", None),
                ("HOUSE_OF_PARLIAMENT", "house", None),
                ("TENURE", "tenure", None),
                ("IDA_NAME", "ida_name", None),
                ("WORK_CATEGORY", "work_category", None),
                ("ACTIVITY_NAME", "activity_name", None),
                ("WORK_DESCRIPTION", "work_description", None),
                ("LETTER_NO", "letter_no", None),
                ("WORK_STAGE", "work_stage", None),
                ("FLAG", "stage_flag", None),
                ("RECOMMENDATION_DATE", "recommendation_date", _parse_date),
                ("SANCTION_DATE", "sanction_date", _parse_date),
                ("ACTUAL_END_DATE", "actual_end_date", _parse_date),
                ("RECOMMENDED_AMOUNT", "recommended_amount", None),
                ("SANCTION_AMOUNT", "sanction_amount", None),
                ("ACTUAL_AMOUNT", "actual_amount", None),
                ("AVERAGE_RATING", "average_rating", None),
                ("ATTACH_ID", "attach_parent_id", None),
                ("FILE_STATUS", "file_status", None),
                ("WORK_ID", "portal_work_id", None),
            ):
                value = row.get(src)
                if value in (None, ""):
                    continue
                record[dst] = transform(value) if transform else value

            record["official_category"] = _official_category(record.get("activity_name"))
            record["work_ref"] = f"MP{record.get('mp_id')}-W{wid}"
            record[f"seen_in_{envelope.replace(' ', '_').lower()}"] = True

    frames = {
        "works": pd.DataFrame(list(works.values())),
        "payments": pd.DataFrame(payments),
        "mp_allocations": pd.DataFrame(allocations),
    }

    counts: dict[str, Any] = {}
    for name, frame in frames.items():
        destination = config.NORMALIZED_ROOT / f"{name}.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if frame.empty:
            log.warning("%s is empty — nothing crawled yet?", name)
        frame.to_parquet(destination, index=False)
        counts[name] = {"rows": int(len(frame)), "path": str(destination)}
        log.info("normalized %-15s %7d rows -> %s", name, len(frame), destination)

    summary = {
        "tables": counts,
        "distinct_works": int(frames["works"]["work_ref"].nunique()) if not frames["works"].empty else 0,
        "provenance": "every row carries source_stored_path and source_sha256",
    }
    store.write_json(obj=summary, destination=config.REPORT_ROOT / "normalize_summary.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return summary
