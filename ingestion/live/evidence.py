"""Evidence without the 300 GB: index the files, stream them on demand.

Measured, not estimated: 25 works carrying attachments yielded **74 files and
79 MB** — 2.96 files a work, 1.07 MB a file — with 37.9% of works carrying any.
Projected over 254,961 national works that is **~286,000 files and ~306 GB**.

(An earlier estimate of 120,000 files / 84 GB was wrong by 3.6x because it asked
the portal for FLAG 1 only. Works sitting at stage 2 keep their files under
FLAG 2 — one had ten there — and FLAG 1 returns nothing for them.)

Storing that was never actually required, and this module is the argument for why.

**Nothing this project trains on is an image.** Verified against `train.py`:

    archetypes      MiniBatchKMeans over 384-d embeddings of the work *description*
    completion risk CoxPHFitter over works.parquet — amounts, dates, stages
    anomaly         IsolationForest over [log_amount, age_days]

Text and numbers, end to end. The photographs and PDFs are **evidence for a
human to look at**, plus exactly one machine use: telling whether the same
picture has been submitted for two different works.

That one use does not need the picture — it needs the picture's *fingerprint*.
A pHash and a dHash are 16 hex characters each. So:

    fetch -> hash -> record the fingerprint -> discard the bytes

turns ~306 GB of storage into ~57 MB, while still catching a re-used photograph
anywhere in the country. The transfer still has to happen once — about 286,000
fetches plus 290,000 listing calls, roughly 11 days at one request a second —
but nothing has to be kept, so it can run on a laptop with 6 GB free.

For display, `fetch_attachment` pulls a single file from the portal at the
moment someone opens a case file. An officer looks at a handful of photographs a
day, not a hundred thousand.

**What this gives up, stated plainly.** Discarding the bytes means we cannot
re-analyse an image later without fetching it again, and we hold no copy if the
portal removes one. Where an image matters as evidence it should be pinned —
`fetch_attachment(..., keep=True)` stores that one file deliberately, which is
the difference between an archive and a hoard.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Iterator

from ingestion import api, config
from ingestion.client import PortalClient, PortalError
from ingestion.live.store import LiveStore
from ingestion.storage.attachments import classify, sniff
from ingestion.storage.manifest import sha256_bytes, utc_now_iso

log = logging.getLogger(__name__)

#: Where deliberately-pinned files go. Everything else is discarded after hashing.
PINNED_ROOT = config.DATA_ROOT / "live" / "pinned"

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    attach_id                  TEXT PRIMARY KEY,
    work_recommendation_dtl_id INTEGER NOT NULL,
    work_ref                   TEXT,
    stage_flag                 INTEGER,
    file_name                  TEXT,
    kind                       TEXT,       -- image | document | unknown
    content_type               TEXT,       -- from magic bytes, not the extension
    file_size                  INTEGER,
    sha256                     TEXT,
    phash                      TEXT,       -- images only
    dhash                      TEXT,
    width                      INTEGER,
    height                     INTEGER,
    indexed_at                 TEXT,
    pinned_path                TEXT,       -- set only where we chose to keep the bytes
    error                      TEXT
);
CREATE INDEX IF NOT EXISTS evidence_work_idx  ON evidence (work_recommendation_dtl_id);
CREATE INDEX IF NOT EXISTS evidence_phash_idx ON evidence (phash);
CREATE INDEX IF NOT EXISTS evidence_sha_idx   ON evidence (sha256);
"""


@dataclass
class IndexCounters:
    works_seen: int = 0
    listed: int = 0
    fetched: int = 0
    images: int = 0
    documents: int = 0
    bytes_transferred: int = 0
    bytes_stored: int = 0
    failed: int = 0
    errors: list[str] = dataclass_field(default_factory=list)


def ensure_schema(store: LiveStore) -> None:
    with store.connect() as conn:
        conn.executescript(SCHEMA)


def _image_size(payload: bytes) -> tuple[int | None, int | None]:
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(payload)) as img:
            return img.size
    except Exception:
        return (None, None)


def _fingerprint(payload: bytes) -> tuple[str | None, str | None]:
    """pHash + dHash, or (None, None) when the bytes are not a readable image."""
    try:
        from mplads import photohash
    except ImportError:
        return (None, None)
    try:
        fp = photohash.fingerprint(payload)
    except Exception as exc:
        log.debug("fingerprint failed: %s", exc)
        return (None, None)
    return (fp.phash, fp.dhash) if fp is not None else (None, None)


def fetch_attachment(client: PortalClient, attach_id: str, *,
                     keep: bool = False) -> tuple[bytes | None, str | None]:
    """Pull one attachment's bytes from the portal. Returns (payload, error).

    `keep=True` writes it under `pinned/` — used where a file is evidence
    somebody has decided matters, not as a default. The default discards.
    """
    try:
        record, _raw = api.get_attachment(client, attach_id)
    except PortalError as exc:
        return None, f"{exc.status}: {exc.detail}"

    b64 = record.get("URL")
    if not b64:
        return None, "response carried no URL field"
    try:
        payload = base64.b64decode(b64)
    except (binascii.Error, ValueError) as exc:
        return None, f"base64 decode failed: {exc}"
    if not payload:
        return None, "decoded to zero bytes"

    if keep:
        name = str(record.get("FILE_NAME") or attach_id)
        target = PINNED_ROOT / attach_id.split(".")[0] / f"{attach_id}__{Path(name).name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    return payload, None


def iter_works_with_attachments(store: LiveStore, limit: int | None = None
                                ) -> Iterator[tuple[int, str | None]]:
    """(work_recommendation_dtl_id, work_ref) for works the portal says have files."""
    sql = ("SELECT work_recommendation_dtl_id, work_ref FROM work "
           "WHERE attach_parent_id IS NOT NULL AND attach_parent_id != 0 "
           "ORDER BY work_recommendation_dtl_id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    with store.connect() as conn:
        for row in conn.execute(sql).fetchall():
            yield int(row["work_recommendation_dtl_id"]), row["work_ref"]


def index_attachments(*, limit_works: int | None = None,
                      store: LiveStore | None = None,
                      pin_documents: bool = False) -> dict[str, Any]:
    """Fetch, fingerprint and discard. Storage stays flat as coverage grows.

    `pin_documents=True` keeps PDFs (sanction orders, completion certificates)
    while still discarding photographs — documents are the smaller half by bytes
    and the half whose *text* is worth re-reading later.
    """
    store = store or LiveStore()
    ensure_schema(store)
    counters = IndexCounters()

    with store.connect() as conn:
        already = {r["attach_id"] for r in
                   conn.execute("SELECT attach_id FROM evidence").fetchall()}

    with PortalClient() as client:
        for work_id, work_ref in iter_works_with_attachments(store, limit_works):
            counters.works_seen += 1

            # The FLAG is a real stage selector and the files are NOT all under
            # FLAG 1. Measured on this portal: works sitting at stage_flag 2 keep
            # their files under FLAG 2 (one work had ten there) with a single
            # further file under FLAG 3, and FLAG 1 returns nothing for them.
            # Asking only FLAG 1 silently collected almost none of the evidence,
            # which is exactly the kind of quiet under-collection that looks like
            # "the portal has few files" rather than like a bug.
            found: dict[str, str] = {}
            for flag in config.ATTACHMENT_FLAGS:
                try:
                    body, _ = api.list_attachments(client, work_id, flag)
                except PortalError as exc:
                    counters.failed += 1
                    counters.errors.append(f"list {work_id} flag {flag}: {exc.detail}")
                    continue
                for record in body if isinstance(body, list) else []:
                    names, ids = record.get("FILE_NAME"), record.get("ATTACH_ID")
                    if names == config.ATTACHMENT_ABSENT or not isinstance(names, list):
                        continue
                    if not isinstance(ids, list) or len(ids) != len(names):
                        continue
                    for name, attach_id in zip(names, ids):
                        if name != "File not available.":
                            found.setdefault(str(attach_id), str(name))

            for attach_id, name in found.items():
                if attach_id in already:
                    continue
                counters.listed += 1

                payload, error = fetch_attachment(client, attach_id)
                if payload is None:
                    counters.failed += 1
                    counters.errors.append(f"{attach_id}: {error}")
                    _record(store, attach_id, work_id, work_ref, str(name),
                            error=error)
                    continue

                counters.fetched += 1
                counters.bytes_transferred += len(payload)
                kind = classify(str(name))
                phash = dhash = None
                width = height = None

                if kind == "image":
                    counters.images += 1
                    phash, dhash = _fingerprint(payload)
                    width, height = _image_size(payload)
                elif kind == "document":
                    counters.documents += 1

                pinned = None
                if pin_documents and kind == "document":
                    target = (PINNED_ROOT / str(work_id)
                              / f"{attach_id}__{Path(str(name)).name}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    pinned = str(target.relative_to(config.DATA_ROOT))
                    counters.bytes_stored += len(payload)

                _record(store, attach_id, work_id, work_ref, str(name),
                        kind=kind, content_type=sniff(payload),
                        file_size=len(payload), sha256=sha256_bytes(payload),
                        phash=phash, dhash=dhash, width=width, height=height,
                        pinned_path=pinned)

                # The bytes go out of scope here. That is the whole point.
                del payload

            if counters.works_seen % 50 == 0:
                log.info("evidence index: %d works, %d files, %.1f MB transferred, "
                         "%.1f MB kept", counters.works_seen, counters.fetched,
                         counters.bytes_transferred / 1e6, counters.bytes_stored / 1e6)

    ratio = (counters.bytes_stored / counters.bytes_transferred
             if counters.bytes_transferred else 0)
    return {
        "works_seen": counters.works_seen,
        "attachments_listed": counters.listed,
        "attachments_fetched": counters.fetched,
        "images": counters.images,
        "documents": counters.documents,
        "megabytes_transferred": round(counters.bytes_transferred / 1e6, 2),
        "megabytes_kept": round(counters.bytes_stored / 1e6, 2),
        "kept_fraction": round(ratio, 4),
        "failed": counters.failed,
        "errors": counters.errors[:20],
        "note": ("Bytes are discarded after fingerprinting. Storage grows with the "
                 "number of files, not their size."),
    }


def _record(store: LiveStore, attach_id: str, work_id: int, work_ref: str | None,
            file_name: str, **fields: Any) -> None:
    with store.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO evidence
               (attach_id, work_recommendation_dtl_id, work_ref, stage_flag, file_name,
                kind, content_type, file_size, sha256, phash, dhash, width, height,
                indexed_at, pinned_path, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (attach_id, work_id, work_ref, fields.get("stage_flag"), file_name,
             fields.get("kind"), fields.get("content_type"), fields.get("file_size"),
             fields.get("sha256"), fields.get("phash"), fields.get("dhash"),
             fields.get("width"), fields.get("height"), utc_now_iso(),
             fields.get("pinned_path"), fields.get("error")),
        )


def reuse_report(store: LiveStore | None = None, *, max_rows: int = 200
                 ) -> list[dict[str, Any]]:
    """The same picture indexed under two different works.

    An exact `phash` match is the cheap, high-confidence case and the only one
    reported here; near-matches need a Hamming distance sweep, which belongs in
    a job rather than a query.

    **This is a question, not a finding.** Two phases of one road legitimately
    look identical from the roadside.
    """
    store = store or LiveStore()
    ensure_schema(store)
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT phash, COUNT(DISTINCT work_recommendation_dtl_id) AS works,
                      COUNT(*) AS files,
                      GROUP_CONCAT(DISTINCT work_ref) AS work_refs
               FROM evidence
               WHERE phash IS NOT NULL
               GROUP BY phash
               HAVING works > 1
               ORDER BY works DESC, files DESC
               LIMIT ?""", (max_rows,)).fetchall()
    return [dict(r) | {
        "caveat": "The same picture under two works is a question for a human, "
                  "not a finding. Two phases of one work look alike."
    } for r in rows]


def coverage(store: LiveStore | None = None) -> dict[str, Any]:
    """How much of the national evidence set has been fingerprinted."""
    store = store or LiveStore()
    ensure_schema(store)
    with store.connect() as conn:
        works_with_files = conn.execute(
            "SELECT COUNT(*) c FROM work WHERE attach_parent_id IS NOT NULL "
            "AND attach_parent_id != 0").fetchone()["c"]
        indexed_works = conn.execute(
            "SELECT COUNT(DISTINCT work_recommendation_dtl_id) c FROM evidence"
        ).fetchone()["c"]
        files = conn.execute("SELECT COUNT(*) c FROM evidence").fetchone()["c"]
        transferred = conn.execute(
            "SELECT COALESCE(SUM(file_size),0) s FROM evidence").fetchone()["s"]
        kept = conn.execute(
            "SELECT COALESCE(SUM(file_size),0) s FROM evidence "
            "WHERE pinned_path IS NOT NULL").fetchone()["s"]
        failed = conn.execute(
            "SELECT COUNT(*) c FROM evidence WHERE error IS NOT NULL").fetchone()["c"]

    return {
        "works_with_attachments": works_with_files,
        "works_indexed": indexed_works,
        "files_indexed": files,
        "megabytes_transferred": round(transferred / 1e6, 2),
        "megabytes_kept_on_disk": round(kept / 1e6, 2),
        "files_failed": failed,
        "index_bytes_per_file": 200,
        "note": ("Fingerprints are held, not files. The index grows by roughly 200 "
                 "bytes a file — about 57 MB for the whole national set — against "
                 "~306 GB to keep the files themselves. Measured at 1.07 MB a file "
                 "over the sample indexed so far."),
    }
