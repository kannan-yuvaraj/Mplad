"""Phase 6 / 7 — enumerate and download every publicly exposed file.

Reads the work rows already crawled, asks the portal what is attached to each
work, and retrieves the bytes. Documents and images go down the same wire (the
portal returns both as base64 from the same endpoint) and are separated by the
declared extension, then confirmed against magic bytes.

Every failure is recorded with URL, identifier, HTTP status, error and retry
count. Nothing is skipped silently.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Iterator

from ingestion import config
from ingestion.client import PortalClient
from ingestion.crawler.checkpoint import Checkpoint
from ingestion.storage import attachments
from ingestion.storage.manifest import RawStore

log = logging.getLogger(__name__)


def iter_crawled_works() -> Iterator[dict[str, Any]]:
    """Every work row already stored under `raw/api/works/`, deduplicated.

    Reads from the preserved raw responses rather than from a normalized table,
    so the attachment crawl can run even if normalization has not.
    """
    root = config.RAW_API / "works"
    if not root.exists():
        return
    seen: set[str] = set()
    for path in sorted(root.rglob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("unreadable stored response %s: %s", path, exc)
            continue
        for envelope_value in body.values():
            rows = json.loads(envelope_value) if isinstance(envelope_value, str) else envelope_value
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                wid = row.get("WORK_RECOMMENDATION_DTL_ID")
                if wid is None or row.get("ATTACH_ID") in (None, "", 0):
                    continue
                if str(wid) in seen:
                    continue
                seen.add(str(wid))
                yield row


def run_attachment_crawl(*, limit_works: int | None = None) -> dict[str, Any]:
    """Download every attachment for every crawled work. Resumable per work."""
    store = RawStore()
    ckpt = Checkpoint.load("attachments")
    known_hashes = store.manifest.known_hashes()

    works = list(iter_crawled_works())
    if limit_works is not None:
        works = works[:limit_works]

    discovered = stored = failed = duplicates = 0
    works_processed = 0

    with PortalClient() as client:
        for row in works:
            wid = str(row["WORK_RECOMMENDATION_DTL_ID"])
            if ckpt.done(wid):
                continue

            refs = attachments.enumerate_attachments(client, wid, store=store)
            discovered += len(refs)

            work_ok = True
            for ref in refs:
                before = len(known_hashes)
                result = attachments.download_attachment(
                    client, ref, store, known_hashes=known_hashes
                )
                if isinstance(result, attachments.AttachmentFailure):
                    failed += 1
                    work_ok = False
                    ckpt.fail(
                        f"{wid}:{ref.attach_id}",
                        url=f"{config.REST_CITIZEN}/getAttachmentById",
                        error=result.error,
                        http_status=result.http_status,
                        retry_count=result.retry_count,
                        identifier=json.dumps(asdict(ref)),
                    )
                    continue
                stored += 1
                if len(known_hashes) == before:
                    duplicates += 1

            works_processed += 1
            if work_ok:
                ckpt.mark(wid)
            if works_processed % 25 == 0:
                log.info("attachments: %d works, %d files stored, %d failed",
                         works_processed, stored, failed)

    ckpt.close()

    summary = {
        "works_with_attachments_discovered": len(works),
        "works_processed_this_run": works_processed,
        "works_completed_total": len(ckpt.completed),
        "attachments_discovered_this_run": discovered,
        "attachments_downloaded_this_run": stored,
        "duplicate_content_detected": duplicates,
        "attachments_failed_this_run": failed,
        "failure_detail": ckpt.failures,
    }
    store.write_json(obj=summary,
                     destination=config.REPORT_ROOT / "attachment_crawl_summary.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return summary
