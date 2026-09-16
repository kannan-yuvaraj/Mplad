"""The live warehouse: current state plus the change feed behind it.

Two things live here, and the second is the one that makes this a monitoring
system rather than a dashboard:

1. **Current state** — `work` and `payment`, upserted every sync.
2. **The change feed** — `change_log`, one row per *field* that actually moved,
   with its old and new value and when we saw it move.

A dashboard that silently overwrites yesterday's number can tell an officer what
is true now. It cannot tell them *"this work moved from Pending for Sanction to
Sanctioned at 14:32, and its sanctioned amount rose by ₹2.1 lakh"* — which is
the thing a monitoring product exists to say. So nothing is overwritten without
first being diffed.

SQLite because it is stdlib, single-file, survives a crash mid-write with WAL,
and the whole live dataset is tens of megabytes. No new dependency.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from ingestion import config
from ingestion.storage.manifest import sha256_bytes, utc_now_iso

log = logging.getLogger(__name__)

LIVE_ROOT = config.DATA_ROOT / "live"
DB_PATH = LIVE_ROOT / "mplads_live.sqlite"

#: Fields we diff and report on. Deliberately not "every column": `Sno` is a
#: row number that shifts whenever anything is inserted above it, and reporting
#: it as a change would bury the real ones in noise.
TRACKED_WORK_FIELDS = (
    "work_stage", "stage_flag", "work_category", "official_category",
    "work_description", "ida_name", "letter_no",
    "recommendation_date", "sanction_date", "actual_end_date",
    "recommended_amount", "sanction_amount", "actual_amount",
    "attach_parent_id", "portal_work_id",
)

TRACKED_PAYMENT_FIELDS = (
    "vendor_id", "vendor_name", "ia_name", "expenditure_date",
    "fund_disbursed_amount", "work_status",
)

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- One row per (state, house, tenure) scope. The cheap fingerprint that tells us
-- whether anything inside it moved, without fetching anything inside it.
CREATE TABLE IF NOT EXISTS scope_watermark (
    combo                  TEXT PRIMARY KEY,
    state_id               INTEGER,
    state_name             TEXT,
    house                  INTEGER,
    tenure_id              INTEGER,
    fingerprint            TEXT,
    tiles_json             TEXT,
    last_checked_at        TEXT,
    last_changed_at        TEXT,
    consecutive_unchanged  INTEGER NOT NULL DEFAULT 0,
    check_count            INTEGER NOT NULL DEFAULT 0,
    change_count           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work (
    work_ref                   TEXT PRIMARY KEY,
    work_recommendation_dtl_id INTEGER NOT NULL,
    mp_id                      INTEGER,
    mp_name                    TEXT,
    state_id                   INTEGER,
    state_name                 TEXT,
    constituency_id            INTEGER,
    constituency               TEXT,
    house                      INTEGER,
    tenure_id                  INTEGER,
    tenure                     TEXT,
    ida_name                   TEXT,
    work_category              TEXT,
    activity_name              TEXT,
    official_category          TEXT,
    work_description           TEXT,
    letter_no                  TEXT,
    work_stage                 TEXT,
    stage_flag                 INTEGER,
    recommendation_date        TEXT,
    sanction_date              TEXT,
    actual_end_date            TEXT,
    recommended_amount         REAL,
    sanction_amount            REAL,
    actual_amount              REAL,
    attach_parent_id           INTEGER,
    portal_work_id             TEXT,
    content_hash               TEXT,
    first_seen_at              TEXT,
    last_seen_at               TEXT,
    last_changed_at            TEXT,
    source_combo               TEXT
);
CREATE INDEX IF NOT EXISTS work_state_idx  ON work (state_id);
CREATE INDEX IF NOT EXISTS work_stage_idx  ON work (work_stage);
CREATE INDEX IF NOT EXISTS work_changed_idx ON work (last_changed_at);

-- Payment grain. A work has many. The natural key the portal gives us is not
-- unique on its own, so the key is hashed from the identifying tuple.
CREATE TABLE IF NOT EXISTS payment (
    payment_key                TEXT PRIMARY KEY,
    work_recommendation_dtl_id INTEGER NOT NULL,
    work_ref                   TEXT,
    vendor_id                  INTEGER,
    vendor_name                TEXT,
    ia_name                    TEXT,
    ida_name                   TEXT,
    expenditure_date           TEXT,
    fund_disbursed_amount      REAL,
    work_status                TEXT,
    state_name                 TEXT,
    mp_name                    TEXT,
    content_hash               TEXT,
    first_seen_at              TEXT,
    last_seen_at               TEXT,
    last_changed_at            TEXT,
    source_combo               TEXT
);
CREATE INDEX IF NOT EXISTS payment_work_idx ON payment (work_recommendation_dtl_id);

-- The change feed. Append-only. This is the product surface.
CREATE TABLE IF NOT EXISTS change_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at  TEXT NOT NULL,
    sync_run_id  INTEGER,
    entity       TEXT NOT NULL,     -- 'work' | 'payment'
    entity_id    TEXT NOT NULL,
    change_type  TEXT NOT NULL,     -- 'appeared' | 'changed' | 'vanished'
    field        TEXT,
    old_value    TEXT,
    new_value    TEXT,
    state_name   TEXT,
    combo        TEXT
);
CREATE INDEX IF NOT EXISTS change_at_idx     ON change_log (observed_at);
CREATE INDEX IF NOT EXISTS change_entity_idx ON change_log (entity, entity_id);
CREATE INDEX IF NOT EXISTS change_field_idx  ON change_log (field);

CREATE TABLE IF NOT EXISTS sync_run (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    mode              TEXT,          -- 'incremental' | 'full'
    scopes_polled     INTEGER DEFAULT 0,
    scopes_changed    INTEGER DEFAULT 0,
    works_seen        INTEGER DEFAULT 0,
    works_appeared    INTEGER DEFAULT 0,
    works_changed     INTEGER DEFAULT 0,
    payments_seen     INTEGER DEFAULT 0,
    payments_appeared INTEGER DEFAULT 0,
    payments_changed  INTEGER DEFAULT 0,
    requests_made     INTEGER DEFAULT 0,
    errors            INTEGER DEFAULT 0,
    error_detail      TEXT,
    ok                INTEGER DEFAULT 0
);
"""


@dataclass
class SyncCounters:
    """Tallies for one sync cycle. Reported, never rounded away."""

    scopes_polled: int = 0
    scopes_changed: int = 0
    works_seen: int = 0
    works_appeared: int = 0
    works_changed: int = 0
    payments_seen: int = 0
    payments_appeared: int = 0
    payments_changed: int = 0
    requests_made: int = 0
    errors: int = 0
    error_detail: list[str] = field(default_factory=list)


def _normalise(value: Any) -> Any:
    """Make a value comparable across fetches.

    Floats that arrive as `2999928.0` one day and `2999928` the next are the same
    number, and reporting that as a change would fill the feed with noise nobody
    can act on.
    """
    if value is None or value == "":
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def content_hash(row: dict[str, Any], fields: Iterable[str]) -> str:
    payload = json.dumps(
        {f: _normalise(row.get(f)) for f in fields},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return sha256_bytes(payload.encode("utf-8"))


def payment_key(row: dict[str, Any]) -> str:
    """Stable identity for a payment.

    The portal gives no payment id. A work can legitimately carry two payments
    of the same amount on the same date to different vendors, so the key is the
    whole identifying tuple hashed — not the amount alone, which would silently
    merge two real disbursements into one.
    """
    parts = (
        row.get("work_recommendation_dtl_id"), row.get("vendor_id"),
        row.get("expenditure_date"), row.get("fund_disbursed_amount"),
        row.get("ia_name"),
    )
    return sha256_bytes(json.dumps(parts, default=str).encode("utf-8"))[:32]


class LiveStore:
    """Read/write access to the live warehouse."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=60)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- sync runs ---------------------------------------------------------

    def start_run(self, mode: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_run (started_at, mode) VALUES (?, ?)",
                (utc_now_iso(), mode),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, counters: SyncCounters, ok: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE sync_run SET finished_at=?, scopes_polled=?, scopes_changed=?,
                       works_seen=?, works_appeared=?, works_changed=?,
                       payments_seen=?, payments_appeared=?, payments_changed=?,
                       requests_made=?, errors=?, error_detail=?, ok=?
                   WHERE id=?""",
                (utc_now_iso(), counters.scopes_polled, counters.scopes_changed,
                 counters.works_seen, counters.works_appeared, counters.works_changed,
                 counters.payments_seen, counters.payments_appeared, counters.payments_changed,
                 counters.requests_made, counters.errors,
                 json.dumps(counters.error_detail[:50], ensure_ascii=False),
                 1 if ok else 0, run_id),
            )

    # -- watermarks --------------------------------------------------------

    def get_watermark(self, combo: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM scope_watermark WHERE combo=?", (combo,)).fetchone()

    def record_check(self, *, combo: str, labels: dict[str, Any],
                     fingerprint: str, tiles: dict[str, Any], changed: bool) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT consecutive_unchanged, check_count, change_count, last_changed_at "
                "FROM scope_watermark WHERE combo=?", (combo,)).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO scope_watermark
                       (combo, state_id, state_name, house, tenure_id, fingerprint,
                        tiles_json, last_checked_at, last_changed_at,
                        consecutive_unchanged, check_count, change_count)
                       VALUES (?,?,?,?,?,?,?,?,?,0,1,?)""",
                    (combo, labels.get("STATE_ID"), labels.get("STATE_NAME"),
                     labels.get("house"), labels.get("tenure_id"), fingerprint,
                     json.dumps(tiles, ensure_ascii=False), now, now, 1 if changed else 0),
                )
                return
            conn.execute(
                """UPDATE scope_watermark
                   SET fingerprint=?, tiles_json=?, last_checked_at=?,
                       last_changed_at=?, consecutive_unchanged=?,
                       check_count=check_count+1, change_count=change_count+?
                   WHERE combo=?""",
                (fingerprint, json.dumps(tiles, ensure_ascii=False), now,
                 now if changed else existing["last_changed_at"],
                 0 if changed else existing["consecutive_unchanged"] + 1,
                 1 if changed else 0, combo),
            )

    def all_watermarks(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM scope_watermark ORDER BY last_checked_at").fetchall()

    # -- upserts -----------------------------------------------------------

    def upsert_works(self, rows: list[dict[str, Any]], *, run_id: int,
                     combo: str, counters: SyncCounters) -> None:
        """Insert or update works, recording every field that actually moved."""
        if not rows:
            return
        now = utc_now_iso()
        columns = [
            "work_ref", "work_recommendation_dtl_id", "mp_id", "mp_name", "state_id",
            "state_name", "constituency_id", "constituency", "house", "tenure_id",
            "tenure", "ida_name", "work_category", "activity_name", "official_category",
            "work_description", "letter_no", "work_stage", "stage_flag",
            "recommendation_date", "sanction_date", "actual_end_date",
            "recommended_amount", "sanction_amount", "actual_amount",
            "attach_parent_id", "portal_work_id",
        ]

        with self.connect() as conn:
            for row in rows:
                ref = row.get("work_ref")
                if not ref:
                    continue
                counters.works_seen += 1
                digest = content_hash(row, TRACKED_WORK_FIELDS)
                existing = conn.execute(
                    "SELECT * FROM work WHERE work_ref=?", (ref,)).fetchone()

                values = [row.get(c) for c in columns]

                if existing is None:
                    conn.execute(
                        f"INSERT INTO work ({', '.join(columns)}, content_hash, "
                        "first_seen_at, last_seen_at, last_changed_at, source_combo) "
                        f"VALUES ({', '.join('?' * len(columns))}, ?, ?, ?, ?, ?)",
                        (*values, digest, now, now, now, combo),
                    )
                    counters.works_appeared += 1
                    conn.execute(
                        """INSERT INTO change_log (observed_at, sync_run_id, entity,
                               entity_id, change_type, state_name, combo)
                           VALUES (?,?,?,?,?,?,?)""",
                        (now, run_id, "work", ref, "appeared", row.get("state_name"), combo),
                    )
                    continue

                if existing["content_hash"] == digest:
                    conn.execute("UPDATE work SET last_seen_at=? WHERE work_ref=?", (now, ref))
                    continue

                # Something moved. Find exactly what, and say so.
                moved = []
                for fname in TRACKED_WORK_FIELDS:
                    before = _normalise(existing[fname] if fname in existing.keys() else None)
                    after = _normalise(row.get(fname))
                    if before != after:
                        moved.append((fname, before, after))

                conn.execute(
                    f"UPDATE work SET {', '.join(c + '=?' for c in columns)}, "
                    "content_hash=?, last_seen_at=?, last_changed_at=?, source_combo=? "
                    "WHERE work_ref=?",
                    (*values, digest, now, now, combo, ref),
                )
                counters.works_changed += 1
                for fname, before, after in moved:
                    conn.execute(
                        """INSERT INTO change_log (observed_at, sync_run_id, entity,
                               entity_id, change_type, field, old_value, new_value,
                               state_name, combo)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (now, run_id, "work", ref, "changed", fname,
                         None if before is None else str(before),
                         None if after is None else str(after),
                         row.get("state_name"), combo),
                    )

    def upsert_payments(self, rows: list[dict[str, Any]], *, run_id: int,
                        combo: str, counters: SyncCounters) -> None:
        if not rows:
            return
        now = utc_now_iso()
        columns = [
            "payment_key", "work_recommendation_dtl_id", "work_ref", "vendor_id",
            "vendor_name", "ia_name", "ida_name", "expenditure_date",
            "fund_disbursed_amount", "work_status", "state_name", "mp_name",
        ]

        with self.connect() as conn:
            for row in rows:
                row = dict(row)
                row["payment_key"] = payment_key(row)
                counters.payments_seen += 1
                digest = content_hash(row, TRACKED_PAYMENT_FIELDS)
                existing = conn.execute(
                    "SELECT * FROM payment WHERE payment_key=?",
                    (row["payment_key"],)).fetchone()
                values = [row.get(c) for c in columns]

                if existing is None:
                    conn.execute(
                        f"INSERT INTO payment ({', '.join(columns)}, content_hash, "
                        "first_seen_at, last_seen_at, last_changed_at, source_combo) "
                        f"VALUES ({', '.join('?' * len(columns))}, ?, ?, ?, ?, ?)",
                        (*values, digest, now, now, now, combo),
                    )
                    counters.payments_appeared += 1
                    conn.execute(
                        """INSERT INTO change_log (observed_at, sync_run_id, entity,
                               entity_id, change_type, field, new_value, state_name, combo)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (now, run_id, "payment", row["payment_key"], "appeared",
                         "fund_disbursed_amount", str(row.get("fund_disbursed_amount")),
                         row.get("state_name"), combo),
                    )
                    continue

                if existing["content_hash"] == digest:
                    conn.execute("UPDATE payment SET last_seen_at=? WHERE payment_key=?",
                                 (now, row["payment_key"]))
                    continue

                moved = [
                    (f, _normalise(existing[f] if f in existing.keys() else None),
                     _normalise(row.get(f)))
                    for f in TRACKED_PAYMENT_FIELDS
                    if _normalise(existing[f] if f in existing.keys() else None)
                    != _normalise(row.get(f))
                ]
                conn.execute(
                    f"UPDATE payment SET {', '.join(c + '=?' for c in columns)}, "
                    "content_hash=?, last_seen_at=?, last_changed_at=?, source_combo=? "
                    "WHERE payment_key=?",
                    (*values, digest, now, now, combo, row["payment_key"]),
                )
                counters.payments_changed += 1
                for fname, before, after in moved:
                    conn.execute(
                        """INSERT INTO change_log (observed_at, sync_run_id, entity,
                               entity_id, change_type, field, old_value, new_value,
                               state_name, combo)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (now, run_id, "payment", row["payment_key"], "changed", fname,
                         None if before is None else str(before),
                         None if after is None else str(after),
                         row.get("state_name"), combo),
                    )

    # -- reads for the API -------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self.connect() as conn:
            counts = {
                "works": conn.execute("SELECT COUNT(*) c FROM work").fetchone()["c"],
                "payments": conn.execute("SELECT COUNT(*) c FROM payment").fetchone()["c"],
                "changes": conn.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"],
                "scopes_tracked": conn.execute(
                    "SELECT COUNT(*) c FROM scope_watermark").fetchone()["c"],
            }
            last = conn.execute(
                "SELECT * FROM sync_run ORDER BY id DESC LIMIT 1").fetchone()
            oldest = conn.execute(
                "SELECT MIN(last_checked_at) m FROM scope_watermark").fetchone()["m"]
            recent = conn.execute(
                "SELECT COUNT(*) c FROM change_log WHERE observed_at > datetime('now','-1 day')"
            ).fetchone()["c"]

        return {
            "counts": counts,
            "changes_last_24h": recent,
            "oldest_scope_checked_at": oldest,
            "last_sync": dict(last) if last else None,
            "database": str(self.path),
        }

    def recent_changes(self, limit: int = 100, entity: str | None = None,
                       field_name: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM change_log"
        where, params = [], []
        if entity:
            where.append("entity=?")
            params.append(entity)
        if field_name:
            where.append("field=?")
            params.append(field_name)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
