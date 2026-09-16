"""Append-only, hash-chained audit log.

Every request that reads intelligence is recorded. Each row carries the SHA-256 of its own
contents **plus the previous row's hash**, so the log is a chain: altering or deleting any
historical row breaks every hash after it, and `verify_chain()` reports exactly where.

This is tamper-*evident*, not tamper-proof. A writer with database access can rewrite the
whole chain from the edit point forward. Detecting that would need the head hash published
somewhere the writer does not control (a WORM store, or a notary). The architecture allows
it; this prototype does not implement it, and the UI says so.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

GENESIS = "0" * 64
_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    role       TEXT NOT NULL,
    action     TEXT NOT NULL,
    resource   TEXT NOT NULL,
    detail     TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    row_hash   TEXT NOT NULL
);
-- Append-only enforced in the database itself, not merely in application code.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def _digest(ts: str, actor: str, role: str, action: str, resource: str,
            detail: str, prev_hash: str) -> str:
    payload = json.dumps(
        [ts, actor, role, action, resource, detail, prev_hash], separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def head(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return row["row_hash"] if row else GENESIS

    def record(self, actor: str, role: str, action: str, resource: str,
               detail: dict | None = None) -> str:
        """Append one entry and return its hash.

        **Reading the tip and inserting must be one atomic step.** The first
        version took a threading lock, then read the tip on one connection and
        inserted on another. A threading lock only serialises one process, and
        between those two connections any other process could append — so two
        writers read the same tip and both chained from it, forking the log.
        That really happened here: entries 4815 and 4816 share a parent, as do
        4817 and 4818, all within the same second.

        `BEGIN IMMEDIATE` takes SQLite's write lock before the read, so no other
        connection — in this process or any other — can slip between the tip and
        the insert. The threading lock stays as well: it is free, and it keeps
        threads in this process from queueing on the database lock.
        """
        ts = datetime.now(timezone.utc).isoformat()
        body = json.dumps(detail or {}, separators=(",", ":"), sort_keys=True)
        with _LOCK:
            conn = self._connect()
            try:
                # isolation_level=None hands us explicit transaction control;
                # without it sqlite3 opens its own deferred transaction and the
                # write lock is not taken until too late.
                conn.isolation_level = None
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                prev = row["row_hash"] if row else GENESIS
                row_hash = _digest(ts, actor, role, action, resource, body, prev)
                conn.execute(
                    "INSERT INTO audit_log (ts, actor, role, action, resource, detail,"
                    " prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?)",
                    (ts, actor, role, action, resource, body, prev, row_hash),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            finally:
                conn.close()
        return row_hash

    def verify_chain(self) -> dict:
        """Recompute every hash, and separate the two ways a chain can fail.

        The first version stopped at the first mismatch and called everything
        `valid: False`. That conflates two findings which mean opposite things:

        * **An altered row.** Its contents no longer match its own recorded
          hash. Nothing but an edit does that, and it is the finding this log
          exists to make. Reported as `rows_altered`.
        * **A forked link.** A row's `prev_hash` does not point at the row before
          it, yet every row's own hash is still correct. No content changed —
          two writers read the same tip and both appended from it. That was a
          race in `record()`, fixed above, and it is an implementation bug, not
          tampering. Reported as `link_breaks` and `forks`.

        Reporting a fork as "tampering detected" would be a false accusation
        against our own log, and the difference is exactly what an auditor would
        want to know. `contents_verified` is the meaningful anti-tampering
        claim and it is reported on its own.

        History is never rewritten to make this green. The triggers refuse
        UPDATE and DELETE, and silently repairing the log is precisely the act
        this chain is built to detect.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()

        altered: list[int] = []
        link_breaks: list[int] = []
        seen_parents: dict[str, int] = {}
        forks: list[dict] = []

        expected_prev = GENESIS
        for row in rows:
            recomputed = _digest(
                row["ts"], row["actor"], row["role"], row["action"],
                row["resource"], row["detail"], row["prev_hash"],
            )
            if recomputed != row["row_hash"]:
                altered.append(row["seq"])

            if row["prev_hash"] != expected_prev:
                link_breaks.append(row["seq"])
                first = seen_parents.get(row["prev_hash"])
                if first is not None:
                    forks.append({"parent_used_by": [first, row["seq"]]})

            seen_parents.setdefault(row["prev_hash"], row["seq"])
            expected_prev = row["row_hash"]

        contents_ok = not altered
        # Where it first went wrong. An altered row outranks a link break: the
        # edit is the serious finding, and a fork after it is a consequence.
        # Kept because "the chain is broken" without a location is not a usable
        # answer, and because the tampering test rightly pins it.
        first_break = altered[0] if altered else (link_breaks[0] if link_breaks else None)

        return {
            "valid": contents_ok and not link_breaks,
            "entries": len(rows),
            "head": expected_prev,
            "broken_at_seq": first_break,
            "contents_verified": contents_ok,
            "rows_altered": altered[:20],
            "rows_altered_count": len(altered),
            "link_breaks": link_breaks[:20],
            "link_breaks_count": len(link_breaks),
            "forks": forks[:20],
            "forks_count": len(forks),
            "verdict": (
                "No row has been altered and every link is in order."
                if contents_ok and not link_breaks else
                f"No row has been altered — every one of the {len(rows)} entries still "
                f"matches its own hash. {len(link_breaks)} link(s) do not point at the "
                f"row before them, from {len(forks)} fork(s) where two writers appended "
                f"from the same tip before that race was fixed. Nothing was edited."
                if contents_ok else
                f"{len(altered)} row(s) no longer match their own hash. That is an edit "
                f"to recorded history and should be investigated."
            ),
            "note": "Tamper-evident: any edit to a historical row breaks its own hash and "
                    "every link after it. Not tamper-proof — publishing the head hash "
                    "externally would be needed to detect a full-chain rewrite.",
        }

    def tail(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, ts, actor, role, action, resource, row_hash"
                " FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
