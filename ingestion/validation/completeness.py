"""The completeness report.

A crawl finishing is not evidence that everything was collected. This report
states, for each dimension, what was discovered and what was actually retrieved,
and lists every failure with its URL, identifier, status and retry count.

It never claims completeness. It reports counts and the gap between them, and
leaves "is that everything?" to a human — the same posture the rest of the
project takes towards its own numbers.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from ingestion import config
from ingestion.crawler.checkpoint import Checkpoint
from ingestion.storage.manifest import ManifestWriter, RawStore

log = logging.getLogger(__name__)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("unreadable %s: %s", path, exc)
        return None


def run_completeness_report() -> dict[str, Any]:
    config.ensure_dirs()
    store = RawStore()
    manifest = ManifestWriter(config.MANIFEST_ROOT / "manifest.jsonl")

    kinds = Counter()
    hashes: set[str] = set()
    duplicate_content = 0
    bytes_stored = 0
    for entry in manifest.read():
        kinds[entry.artefact_kind] += 1
        if entry.sha256 in hashes:
            duplicate_content += 1
        hashes.add(entry.sha256)
        bytes_stored += entry.file_size

    states = _read_json(config.RAW_API / "reference" / "states.json") or []
    const_dir = config.RAW_API / "reference" / "constituencies"
    mps_dir = config.RAW_API / "reference" / "mps"

    constituencies_discovered = 0
    states_with_constituencies = 0
    if const_dir.exists():
        for path in const_dir.glob("*.json"):
            rows = _read_json(path) or []
            constituencies_discovered += len(rows)
            states_with_constituencies += 1

    mp_ids: set[Any] = set()
    if mps_dir.exists():
        for path in mps_dir.glob("*.json"):
            for row in _read_json(path) or []:
                mp_ids.add(row.get("ID"))

    works_discovered: set[str] = set()
    works_root = config.RAW_API / "works"
    scope_units = 0
    if works_root.exists():
        for path in works_root.rglob("*.json"):
            scope_units += 1
            body = _read_json(path) or {}
            for value in body.values():
                rows = json.loads(value) if isinstance(value, str) else value
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if isinstance(row, dict) and "WORK_RECOMMENDATION_DTL_ID" in row:
                        works_discovered.add(str(row["WORK_RECOMMENDATION_DTL_ID"]))

    documents_stored = sum(1 for _ in config.RAW_DOCUMENTS.rglob("*")
                           if _.is_file()) if config.RAW_DOCUMENTS.exists() else 0
    images_stored = sum(1 for _ in config.RAW_IMAGES.rglob("*")
                        if _.is_file()) if config.RAW_IMAGES.exists() else 0

    checkpoints = {
        name: Checkpoint.load(name) for name in ("enumerate", "works", "attachments")
    }
    failures: list[dict[str, Any]] = []
    for name, ckpt in checkpoints.items():
        for failure in ckpt.failures:
            failures.append({"stage": name, **failure})

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "states": {
            "discovered": len(states),
            "processed_for_constituencies": states_with_constituencies,
        },
        "constituencies": {"discovered": constituencies_discovered},
        "mps": {"discovered": len(mp_ids)},
        "works": {
            "scope_responses_stored": scope_units,
            "distinct_works_discovered": len(works_discovered),
        },
        "documents": {"stored": documents_stored},
        "images": {"stored": images_stored},
        "raw_store": {
            "manifest_entries": sum(kinds.values()),
            "by_kind": dict(kinds),
            "distinct_content_hashes": len(hashes),
            "duplicate_content_entries": duplicate_content,
            "bytes_stored": bytes_stored,
        },
        "checkpoints": {
            name: {"completed_units": len(c.completed), "failures": len(c.failures)}
            for name, c in checkpoints.items()
        },
        "failures": failures,
        "completeness_claim": (
            "NOT CLAIMED. This report states what was discovered and what was "
            "retrieved. Enumeration is exhaustive only if every state, house and "
            "tenure scope in `checkpoints.works.completed_units` equals the "
            "planned scope count in reports/work_crawl_summary.json, every "
            "failure above has been resolved, and reports/reconciliation.json "
            "shows no unexplained mismatch."
        ),
    }

    store.write_json(obj=report, destination=config.REPORT_ROOT / "completeness.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return report
