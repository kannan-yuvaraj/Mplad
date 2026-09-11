"""Resumability (Phase 8).

If the crawler dies after 10,000 records, restarting must not start from zero.

**Append-only by design.** The first version rewrote the entire completed set as
one sorted JSON document after every unit. That is O(n) per mark and so O(n²)
across a crawl — at ~72,000 attachment works it would rewrite a multi-megabyte
document 72,000 times, tens of gigabytes of pointless writes, getting slower the
longer the run goes. A multi-day crawl cannot be built on that.

So completed keys are appended to a JSONL log one line at a time (O(1) per mark)
and the readable summary is refreshed only periodically and at close. A kill -9
loses at most the summary, never the completed keys: the log is the source of
truth and the summary is rebuilt from it on load.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from ingestion import config
from ingestion.storage.manifest import utc_now_iso

log = logging.getLogger(__name__)

#: How often to refresh the human-readable summary during a long run.
SUMMARY_EVERY = 250

#: The summary keeps only the most recent failures; the JSONL log keeps them all.
SUMMARY_FAILURE_LIMIT = 500


@dataclass
class Checkpoint:
    """Completed unit keys and recorded failures for one crawl stage."""

    name: str
    completed: set[str] = field(default_factory=set)
    failures: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    _handle: TextIO | None = field(default=None, repr=False, compare=False)
    _since_summary: int = field(default=0, repr=False, compare=False)

    # -- paths -------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Readable summary. Derived — never the source of truth."""
        return config.CHECKPOINT_ROOT / f"{self.name}.json"

    @property
    def log_path(self) -> Path:
        """Append-only completed-keys log. This *is* the source of truth."""
        return config.CHECKPOINT_ROOT / f"{self.name}.completed.jsonl"

    @property
    def failures_path(self) -> Path:
        """Append-only failure log."""
        return config.CHECKPOINT_ROOT / f"{self.name}.failures.jsonl"

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, name: str) -> "Checkpoint":
        config.ensure_dirs()
        ckpt = cls(name=name)

        # Runs started before this change stored everything in the summary JSON.
        # Read it first so an in-progress crawl is not restarted from zero.
        if ckpt.path.exists():
            try:
                blob = json.loads(ckpt.path.read_text(encoding="utf-8"))
                ckpt.completed.update(blob.get("completed", []))
                ckpt.failures.extend(blob.get("failures", []))
                ckpt.started_at = blob.get("started_at", ckpt.started_at)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("checkpoint summary %s unreadable (%s); relying on the log",
                            ckpt.path, exc)

        if ckpt.log_path.exists():
            with ckpt.log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        ckpt.completed.add(line)

        if ckpt.failures_path.exists():
            seen = {json.dumps(f, sort_keys=True) for f in ckpt.failures}
            with ckpt.failures_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        blob = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if json.dumps(blob, sort_keys=True) not in seen:
                        ckpt.failures.append(blob)

        log.info("checkpoint %s: %d completed, %d failures",
                 name, len(ckpt.completed), len(ckpt.failures))
        return ckpt

    # -- writing -----------------------------------------------------------

    def _log_handle(self) -> TextIO:
        if self._handle is None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.log_path.open("a", encoding="utf-8")
        return self._handle

    def done(self, key: str) -> bool:
        return key in self.completed

    def mark(self, key: str) -> None:
        """Record a completed unit. O(1) — one line appended and flushed."""
        if key in self.completed:
            return
        self.completed.add(key)
        handle = self._log_handle()
        handle.write(key + "\n")
        handle.flush()

        self._since_summary += 1
        if self._since_summary >= SUMMARY_EVERY:
            self.save()

    def fail(self, key: str, *, url: str, error: str,
             http_status: int | None = None, retry_count: int = 0,
             identifier: str | None = None) -> None:
        """Record a failure. Never silently skip — the completeness report reads this."""
        record = {
            "key": key,
            "identifier": identifier,
            "url": url,
            "http_status": http_status,
            "error": error,
            "retry_count": retry_count,
            "at": utc_now_iso(),
        }
        self.failures.append(record)
        self.failures_path.parent.mkdir(parents=True, exist_ok=True)
        with self.failures_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save(self) -> None:
        """Refresh the summary. Atomic: temp file then replace.

        The completed keys are deliberately *not* inlined here — at 72,000 keys
        they are noise in a file meant for a person, and the JSONL log already
        holds every one of them.
        """
        self.updated_at = utc_now_iso()
        self._since_summary = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_count": len(self.completed),
            "failure_count": len(self.failures),
            "completed_keys_are_in": self.log_path.name,
            "all_failures_are_in": self.failures_path.name,
            "failures": self.failures[-SUMMARY_FAILURE_LIMIT:],
            "failures_truncated": len(self.failures) > SUMMARY_FAILURE_LIMIT,
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def close(self) -> None:
        """Flush and refresh the summary. Safe to call more than once."""
        self.save()
        if self._handle is not None:
            self._handle.close()
            self._handle = None
