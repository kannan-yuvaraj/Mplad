"""Raw preservation and the audit manifest (Phase 5 / Phase 14).

Two rules this module exists to enforce:

1. **Nothing is stored without a manifest entry.** `RawStore.write` is the only
   way bytes reach disk in this package, and it always appends a manifest row.
2. **A manifest row is enough to re-derive the field.** Source URL, request
   body, identifiers, timestamp, HTTP status, content type, size and SHA-256
   are all recorded, so any downstream number can be traced back to the exact
   response it came from.

The manifest is JSONL: append-only, survives a crash mid-crawl, and can be read
back with a one-line `pandas.read_json(..., lines=True)`.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ingestion import config


def sha256_bytes(payload: bytes) -> str:
    """SHA-256 of a payload, lowercase hex."""
    return hashlib.sha256(payload).hexdigest()


def utc_now_iso() -> str:
    """Retrieval timestamp, UTC, ISO-8601 with explicit offset."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One retrieved artefact. Every field is provenance, not decoration."""

    #: Where the bytes landed, relative to the ingestion data root.
    stored_path: str
    #: Fully-qualified source URL.
    source_url: str
    #: HTTP method used.
    http_method: str
    #: Request body, verbatim, so the call is reproducible.
    request_body: str | None
    #: HTTP status actually returned.
    http_status: int
    #: Content-Type header as returned by the server.
    content_type: str | None
    #: Bytes on disk.
    file_size: int
    #: SHA-256 of the bytes on disk.
    sha256: str
    #: When we retrieved it.
    retrieved_at: str
    #: What kind of artefact this is: api | document | image | page.
    artefact_kind: str
    #: Source-provided identifiers. Whatever the source gave us, unmodified.
    identifiers: dict[str, Any] = field(default_factory=dict)
    #: Free-form note (e.g. "grand-total row stripped", "sentinel N/A").
    note: str | None = None


class ManifestWriter:
    """Append-only JSONL manifest writer. Thread-safe, though the crawler is
    single-threaded on purpose."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, entry: ManifestEntry) -> None:
        line = json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read(self) -> Iterator[ManifestEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield ManifestEntry(**json.loads(line))

    def known_hashes(self) -> set[str]:
        """Every SHA-256 already stored — the duplicate-detection index."""
        return {entry.sha256 for entry in self.read()}

    def count(self) -> int:
        return sum(1 for _ in self.read())


class RawStore:
    """The only writer of raw bytes in this package.

    Deduplicates by content hash: if the identical bytes are already stored at
    the identical path, the write is skipped but the manifest still records the
    retrieval, so a re-crawl is visible without inflating storage.
    """

    def __init__(self, manifest_name: str = "manifest.jsonl") -> None:
        config.ensure_dirs()
        self.manifest = ManifestWriter(config.MANIFEST_ROOT / manifest_name)

    def write(
        self,
        *,
        payload: bytes,
        destination: Path,
        source_url: str,
        artefact_kind: str,
        http_status: int,
        content_type: str | None = None,
        http_method: str = "POST",
        request_body: str | None = None,
        identifiers: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> ManifestEntry:
        """Persist `payload` at `destination` and record it in the manifest."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256_bytes(payload)

        already = destination.exists() and sha256_bytes(destination.read_bytes()) == digest
        if not already:
            destination.write_bytes(payload)

        try:
            stored = str(destination.relative_to(config.DATA_ROOT))
        except ValueError:
            stored = str(destination)

        entry = ManifestEntry(
            stored_path=stored,
            source_url=source_url,
            http_method=http_method,
            request_body=request_body,
            http_status=http_status,
            content_type=content_type,
            file_size=len(payload),
            sha256=digest,
            retrieved_at=utc_now_iso(),
            artefact_kind=artefact_kind,
            identifiers=identifiers or {},
            note=note if not already else (note or "") + " [bytes unchanged since last retrieval]",
        )
        self.manifest.append(entry)
        return entry

    def write_json(self, *, obj: Any, destination: Path, **kwargs: Any) -> ManifestEntry:
        """Convenience wrapper for JSON we produced rather than received."""
        payload = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        return self.write(payload=payload, destination=destination, **kwargs)
