"""Package everything collected into a distributable dataset.

Mirrors the structure of the existing `Dataset/` package the project already
uses — `raw/`, `processed/`, `metadata/` — so a consumer who knows one knows the
other. Nothing here fetches; it reads the preserved raw responses and the
normalized tables and assembles a package with a data dictionary and a hash
manifest.

The package is regenerable from `data/portal/raw/` alone. If a number in it is
ever questioned, the chain is: table row -> `source_stored_path` -> the exact
preserved API response -> the manifest row naming URL, request body and
retrieval timestamp.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from ingestion import config
from ingestion.storage.manifest import ManifestWriter, RawStore, sha256_bytes, utc_now_iso

log = logging.getLogger(__name__)

DATASET_ROOT = config.DATA_ROOT / "dataset"


def _read_reference() -> dict[str, pd.DataFrame]:
    """states, tenures, constituencies and MPs from the preserved responses."""
    ref = config.RAW_API / "reference"
    out: dict[str, pd.DataFrame] = {}

    states_file = ref / "states.json"
    if states_file.exists():
        out["states"] = pd.DataFrame(json.loads(states_file.read_text(encoding="utf-8")))

    tenures: list[dict[str, Any]] = []
    for house in config.HOUSES:
        path = ref / f"tenures_house{house}.json"
        if path.exists():
            for row in json.loads(path.read_text(encoding="utf-8")):
                tenures.append({"tenure_id": row["ID"], "caption": row["CAPTION"], "house": house})
    if tenures:
        out["tenures"] = pd.DataFrame(tenures)

    consts: list[dict[str, Any]] = []
    for path in sorted((ref / "constituencies").glob("state_*.json")):
        state_id = int(path.stem.split("_")[1])
        for row in json.loads(path.read_text(encoding="utf-8")):
            consts.append({"constituency_id": row["ID"], "constituency_name": row["CAPTION"],
                           "state_id": state_id})
    if consts:
        out["constituencies"] = pd.DataFrame(consts)

    mps: list[dict[str, Any]] = []
    for path in sorted((ref / "mps").glob("state_*.json")):
        parts = path.stem.split("_")
        state_id, house, tenure_id = int(parts[1]), int(parts[3]), int(parts[5])
        for row in json.loads(path.read_text(encoding="utf-8")):
            mps.append({"mp_id": row["ID"], "mp_name": row["CAPTION"], "state_id": state_id,
                        "house": house, "tenure_id": tenure_id})
    if mps:
        out["mps"] = pd.DataFrame(mps).drop_duplicates(subset=["mp_id", "tenure_id"])

    return out


def _file_index() -> tuple[pd.DataFrame, pd.DataFrame]:
    """documents and images tables, built from the audit manifest."""
    manifest = ManifestWriter(config.MANIFEST_ROOT / "manifest.jsonl")
    docs: list[dict[str, Any]] = []
    imgs: list[dict[str, Any]] = []

    for entry in manifest.read():
        if entry.artefact_kind not in {"document", "image"}:
            continue
        ident = entry.identifiers
        row = {
            "work_recommendation_dtl_id": ident.get("WORK_RECOMMENDATION_DTL_ID"),
            "attach_id": ident.get("ATTACH_ID"),
            "attach_parent_id": ident.get("ATTACH_PARENT_ID"),
            "stage_flag": ident.get("FLAG"),
            "file_name": ident.get("FILE_NAME"),
            "declared_extension": ident.get("declared_extension"),
            "content_type": entry.content_type,
            "file_size": entry.file_size,
            "sha256": entry.sha256,
            "stored_path": entry.stored_path,
            "source_url": entry.source_url,
            "retrieved_at": entry.retrieved_at,
            "note": entry.note,
        }
        (imgs if entry.artefact_kind == "image" else docs).append(row)

    def frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        f = pd.DataFrame(rows)
        return f.drop_duplicates(subset=["attach_id"]) if not f.empty else f

    images = frame(imgs)
    if not images.empty:
        # The portal declares no BEFORE/DURING/AFTER. Column present, always
        # null, so a consumer sees the absence rather than inventing it.
        images["source_declared_stage"] = pd.NA
    return frame(docs), images


def _portal_aggregates() -> pd.DataFrame:
    """The dashboard's own published tile numbers, for reconciliation."""
    rows: list[dict[str, Any]] = []
    tiles_dir = config.RAW_API / "tiles"
    if tiles_dir.exists():
        for path in sorted(tiles_dir.rglob("*.json")):
            body = json.loads(path.read_text(encoding="utf-8"))
            for tile, value in body.items():
                if not isinstance(value, list):
                    continue
                rows.append({"scope": path.stem, "tile": tile,
                             "raw_value": json.dumps(value, ensure_ascii=False)})
    return pd.DataFrame(rows)


DICTIONARY = {
    "works": [
        ("work_ref", "text", "Canonical key, MP<mp_id>-W<work_recommendation_dtl_id>."),
        ("work_recommendation_dtl_id", "int", "Portal's recommendation-detail id. Not unique alone — the serial restarts per MP."),
        ("mp_id", "int", "MP id from getMpNamesData."),
        ("portal_work_id", "text", "The portal's own WORK_ID. Issued only at completion; null on every open work. DO NOT JOIN ON THIS."),
        ("state_id / state_name", "int / text", "State or UT."),
        ("constituency_id / constituency", "int / text", "Parliamentary constituency."),
        ("house", "int", "2 = Lok Sabha, 1 = Rajya Sabha."),
        ("tenure_id / tenure", "int / text", "17th LS = 5, 18th LS = 7; RS Sitting = 1, Retired = 2."),
        ("ida_name", "text", "District authority office. NOT a district name — it is an office."),
        ("work_category", "text", "Portal's coarse category, e.g. Normal/Others, Trust and Society."),
        ("activity_name", "text", "Composite: WS/MP<code>/<FY>/<serial>-<official category>."),
        ("official_category", "text", "Parsed tail of activity_name. The interpretable category axis."),
        ("work_description", "text", "Free text written by the recommending MP's office."),
        ("letter_no", "text", "Recommendation letter number."),
        ("work_stage", "text", "Portal's current stage label, e.g. Pending for Sanction, Physical Inspection."),
        ("stage_flag", "int", "Portal FLAG. 1 on recommended/sanctioned rows, 3 on completed. Full meaning NOT established."),
        ("recommendation_date", "date", "Date the MP recommended the work."),
        ("sanction_date", "date", "Sanction row's date. In the CSV snapshot this copies recommendation_date on 100% of works — verify before treating as a real sanction timestamp."),
        ("actual_end_date", "date", "Portal's completion date. May disagree with the completion certificate — see FINDINGS.md §9."),
        ("recommended_amount", "float", "Rupees recommended by the MP."),
        ("sanction_amount", "float", "Rupees sanctioned by the district authority."),
        ("actual_amount", "float", "Rupees recorded at completion. Read DATA_CONTRACT §6 and FINDINGS.md §6 before using as expenditure."),
        ("average_rating", "float", "Citizen star rating. Mostly 0."),
        ("attach_parent_id", "int", "Parent ATTACH_ID; join to documents/images on attach_parent_id."),
        ("source_stored_path / source_sha256", "text", "Provenance: the exact preserved response this row came from."),
    ],
    "payments": [
        ("work_recommendation_dtl_id", "int", "Work this payment belongs to."),
        ("vendor_id / vendor_name", "int / text", "The vendor paid. NOT present in the CSV snapshot — live portal only."),
        ("ia_name", "text", "Implementing agency executing the work."),
        ("ida_name", "text", "District authority office."),
        ("expenditure_date", "date", "Date of the disbursement."),
        ("fund_disbursed_amount", "float", "Rupees released to the vendor."),
        ("work_status", "text", "Payment state, e.g. Payment Success."),
        ("portal_work_id", "text", "Portal's WORK_ID string form on payment rows."),
        ("source_stored_path / source_sha256", "text", "Provenance."),
    ],
    "documents": [
        ("attach_id", "text", "Compound <parent>.<child>. The bare parent will not retrieve a file."),
        ("work_recommendation_dtl_id", "int", "Work the file belongs to."),
        ("stage_flag", "int", "FLAG the listing came back under."),
        ("file_name", "text", "Filename as the uploading agency named it. Not a reliable description of contents."),
        ("content_type", "text", "Confirmed from magic bytes, not from the extension."),
        ("file_size / sha256", "int / text", "Bytes and content hash."),
        ("stored_path", "text", "Path under data/portal/, relative."),
        ("source_url / retrieved_at", "text", "Provenance."),
    ],
    "images": [
        ("source_declared_stage", "text", "ALWAYS NULL. The portal declares no BEFORE/DURING/AFTER. Do not infer it — see LIMITATIONS.md §4."),
        ("(all other columns)", "", "Same as documents."),
    ],
}


def _write_dictionary(path: Path, tables: dict[str, pd.DataFrame]) -> None:
    lines = [
        "# Data dictionary — MPLADS eSAKSHI public-portal dataset",
        "",
        f"Generated {utc_now_iso()} from `data/portal/raw/`.",
        "",
        "Every table carries `source_stored_path` and `source_sha256` where it was",
        "derived from an API response, so any value can be traced to the exact",
        "preserved body it came from.",
        "",
        "## Tables",
        "",
        "| Table | Rows | Grain |",
        "|---|---:|---|",
    ]
    grain = {
        "works": "one row per work",
        "payments": "one row per vendor payment (several per work)",
        "mp_allocations": "one row per MP per tenure",
        "documents": "one row per non-image file",
        "images": "one row per image file",
        "states": "one row per state/UT",
        "constituencies": "one row per constituency",
        "mps": "one row per MP per tenure",
        "tenures": "one row per tenure per house",
        "portal_aggregates": "the dashboard's own published tile values",
    }
    for name, frame in sorted(tables.items()):
        lines.append(f"| `{name}` | {len(frame):,} | {grain.get(name, '')} |")

    for table, cols in DICTIONARY.items():
        lines += ["", f"## `{table}`", "", "| Column | Type | Meaning |", "|---|---|---|"]
        lines += [f"| `{c}` | {t} | {d} |" for c, t, d in cols]

    lines += [
        "", "## Things a consumer must not get wrong", "",
        "1. **Join on `(work_recommendation_dtl_id, mp_id)`**, never `portal_work_id`.",
        "2. **`actual_amount` is not straightforwardly expenditure.** `payments.fund_disbursed_amount` is the vendor money actually released.",
        "3. **`ida_name` is a district office, not a district.** There is no district dimension.",
        "4. **`images.source_declared_stage` is always null** and that is correct.",
        "5. **The portal's own grand-total row has been removed** from every table. It was never a work.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_build_dataset() -> dict[str, Any]:
    """Assemble the package. Reads only from disk."""
    config.ensure_dirs()
    store = RawStore()
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    (DATASET_ROOT / "tables").mkdir(exist_ok=True)
    (DATASET_ROOT / "metadata").mkdir(exist_ok=True)

    tables: dict[str, pd.DataFrame] = {}

    for name in ("works", "payments", "mp_allocations"):
        path = config.NORMALIZED_ROOT / f"{name}.parquet"
        if path.exists():
            tables[name] = pd.read_parquet(path)

    tables.update(_read_reference())
    docs, imgs = _file_index()
    if not docs.empty:
        tables["documents"] = docs
    if not imgs.empty:
        tables["images"] = imgs
    aggregates = _portal_aggregates()
    if not aggregates.empty:
        tables["portal_aggregates"] = aggregates

    written: dict[str, Any] = {}
    for name, frame in tables.items():
        pq = DATASET_ROOT / "tables" / f"{name}.parquet"
        csv = DATASET_ROOT / "tables" / f"{name}.csv"
        frame.to_parquet(pq, index=False)
        frame.to_csv(csv, index=False, encoding="utf-8")
        written[name] = {"rows": int(len(frame)), "columns": int(frame.shape[1])}
        log.info("dataset table %-20s %8d rows x %3d cols", name, len(frame), frame.shape[1])

    _write_dictionary(DATASET_ROOT / "metadata" / "DATA_DICTIONARY.md", tables)

    # Hash manifest over every file in the package.
    files: list[dict[str, Any]] = []
    for path in sorted(DATASET_ROOT.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            payload = path.read_bytes()
            files.append({
                "path": str(path.relative_to(DATASET_ROOT)).replace("\\", "/"),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            })

    kinds = Counter()
    total_bytes = 0
    for root, kind in ((config.RAW_DOCUMENTS, "documents"), (config.RAW_IMAGES, "images")):
        if root.exists():
            for f in root.rglob("*"):
                if f.is_file():
                    kinds[kind] += 1
                    total_bytes += f.stat().st_size

    manifest = {
        "generated_at": utc_now_iso(),
        "source": "https://mplads.mospi.gov.in public REST API (unauthenticated)",
        "attribution": "MPLADS / Ministry of Statistics and Programme Implementation, "
                       "Government of India. No licence is declared on the portal — "
                       "attribute and state the retrieval date; do not assert redistribution rights.",
        "tables": written,
        "package_files": files,
        "binary_files": {"counts": dict(kinds), "bytes": total_bytes},
        "provenance": "Every table row carries source_stored_path + source_sha256. "
                      "The full audit trail is data/portal/manifests/manifest.jsonl.",
    }
    (DATASET_ROOT / "metadata" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    store.write_json(obj={"tables": written, "binary_files": manifest["binary_files"]},
                     destination=config.REPORT_ROOT / "dataset_build.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")

    return {"dataset_root": str(DATASET_ROOT), "tables": written,
            "binary_files": manifest["binary_files"]}
