"""Field verification: what an officer found when they actually went and looked.

This closes the only open loop in the product. Everything upstream ends at *"a human should
check X"*; this records what the human found. The record is the officer's own observation —
not government data we invented — and it is attributed, timestamped and immutable.

**Why this matters more than it looks.** The project's central honest limitation is that no
fraud labels exist, so nothing can be validated against real outcomes. Verification records
are exactly those labels, accumulating one site visit at a time. Enough of them and the
weights in `config.SIGNAL_WEIGHTS` stop being reasoned defaults and start being fitted to
what officers actually confirmed.

We do not pretend that has happened. `label_readiness()` reports honestly how far off it is.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mplads import config, photohash

LOGGER = logging.getLogger(__name__)

DB = config.ARTIFACTS / "field_verifications.sqlite"
PHOTOS = config.ARTIFACTS / "field_photos"
DOCUMENTS = config.ARTIFACTS / "field_documents"

#: What an officer can report. Deliberately includes the outcomes that clear a work —
#: a verification tool that can only confirm suspicion is a tool for confirming suspicion.
OUTCOMES: dict[str, str] = {
    "VERIFIED_COMPLETE": "Visited. The work exists and is complete as recorded.",
    "VERIFIED_IN_PROGRESS": "Visited. The work exists and is genuinely under way.",
    "NOT_STARTED": "Visited. No work has begun at this location.",
    "NOT_FOUND": "Visited. Nothing at this location matches the record.",
    "RECORD_MISMATCH": "The work exists but differs from the record (scope, size or place).",
    "NO_ACCESS": "Could not verify — site inaccessible or location unclear.",
}

#: Outcomes that would count as the system having been useful, if we were scoring it.
CONFIRMS_CONCERN = {"NOT_STARTED", "NOT_FOUND", "RECORD_MISMATCH"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS verification (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    work_ref    TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    photo       TEXT,
    ocr_text    TEXT,
    actor       TEXT NOT NULL,
    role        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    row_hash    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verification_work ON verification(work_ref);
-- A field record is evidence. It is corrected by superseding it, never by editing it.
CREATE TRIGGER IF NOT EXISTS verification_no_update
BEFORE UPDATE ON verification
BEGIN SELECT RAISE(ABORT, 'verification records are immutable; add a new one'); END;
CREATE TRIGGER IF NOT EXISTS verification_no_delete
BEFORE DELETE ON verification
BEGIN SELECT RAISE(ABORT, 'verification records are immutable; add a new one'); END;

-- Photographs are fingerprinted on upload, before any verification is written, so an
-- officer is told about a re-used picture while they still have the site in front of them.
CREATE TABLE IF NOT EXISTS photo (
    name            TEXT PRIMARY KEY,
    phash           TEXT NOT NULL,
    dhash           TEXT NOT NULL,
    first_work_ref  TEXT,
    first_actor     TEXT,
    first_seen      TEXT NOT NULL
);
"""

#: Columns added after the first version shipped. SQLite has no "ADD COLUMN IF NOT EXISTS",
#: so we look before we leap rather than catching the error and hoping it was this one.
MIGRATIONS: dict[str, str] = {
    "phash": "ALTER TABLE verification ADD COLUMN phash TEXT",
    "dhash": "ALTER TABLE verification ADD COLUMN dhash TEXT",
    "demo": "ALTER TABLE verification ADD COLUMN demo INTEGER NOT NULL DEFAULT 0",
    # What the camera actually saw, kept separately from what was verified. The two
    # disagreeing is the single most useful thing a photograph can tell us, and storing
    # only the resolved answer throws that away — a board reading one digit wrong at 99.6%
    # confidence lands on a different real work, and that has to survive into the record.
    "board_ref": "ALTER TABLE verification ADD COLUMN board_ref TEXT",
    "board_amount": "ALTER TABLE verification ADD COLUMN board_amount REAL",
    "ocr_confidence": "ALTER TABLE verification ADD COLUMN ocr_confidence REAL",
    "needed_confirmation":
        "ALTER TABLE verification ADD COLUMN needed_confirmation INTEGER NOT NULL DEFAULT 0",
    "photo_reuse_count":
        "ALTER TABLE verification ADD COLUMN photo_reuse_count INTEGER NOT NULL DEFAULT 0",
    "reused_from": "ALTER TABLE verification ADD COLUMN reused_from TEXT",
    # Which reader read the board, and whether a second, independent reader agreed. Two
    # engines reading the same reference is corroboration; one engine at "99%" is not.
    "ocr_engine": "ALTER TABLE verification ADD COLUMN ocr_engine TEXT",
    "readers_agree": "ALTER TABLE verification ADD COLUMN readers_agree INTEGER",
    # A sanction order, work order or certificate the officer attached, read by Docling.
    "document": "ALTER TABLE verification ADD COLUMN document TEXT",
}


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(verification)")}
    for column, statement in MIGRATIONS.items():
        if column not in existing:
            conn.execute(statement)
            LOGGER.info("migrated verification store: added %s", column)
    conn.commit()
    return conn


def save_photo(data: bytes, filename: str) -> str:
    """Store an uploaded photo under a content hash, so the same photo is stored once."""
    PHOTOS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:24]
    suffix = Path(filename).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError(f"unsupported image type: {suffix}")
    path = PHOTOS / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    return path.name


def save_document(data: bytes, filename: str) -> str:
    """Store an uploaded document (sanction order, work order, certificate) under a content
    hash, the same way photographs are stored — once, and never under a name the uploader
    chose, so a crafted filename cannot reach outside the folder."""
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:24]
    suffix = Path(filename).suffix.lower() or ".pdf"
    if suffix not in config.DOCUMENT_SUFFIXES:
        raise ValueError(f"unsupported document type: {suffix}")
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        raise ValueError("this file is named .pdf but is not a PDF")
    path = DOCUMENTS / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(data)
    return path.name


def check_photo(data: bytes, name: str, work_ref: str, actor: str = "anonymous") -> dict:
    """Fingerprint an uploaded photograph and report earlier submissions of the same picture.

    Called at upload time, not at save time, so the officer learns about a re-used photo
    while they are still standing at the site and can look again.

    Re-use is only reported across *different* works. Photographing the same work twice is
    normal and expected; it is the same picture appearing under two sanctions that is worth
    a human's attention — and even then it is often innocent (two phases of one road, two
    works at one school), which is why this returns evidence rather than a conclusion.
    """
    fp = photohash.fingerprint(data)
    if fp is None:
        return {"fingerprinted": False, "reuse": []}

    with _connect() as conn:
        rows = conn.execute("SELECT * FROM photo").fetchall()
        reuse = []
        for row in rows:
            if row["first_work_ref"] == work_ref:
                continue
            match = photohash.compare(fp, {"phash": row["phash"], "dhash": row["dhash"]})
            if match["match"]:
                reuse.append({
                    "work_ref": row["first_work_ref"],
                    "photo": row["name"],
                    "first_seen": row["first_seen"],
                    "actor": row["first_actor"],
                    "exact_file": row["name"] == name,
                    **match,
                })
        reuse.sort(key=lambda r: (r["phash_distance"] + r["dhash_distance"]))

        conn.execute(
            "INSERT OR IGNORE INTO photo (name, phash, dhash, first_work_ref, first_actor,"
            " first_seen) VALUES (?,?,?,?,?,?)",
            (name, fp.phash, fp.dhash, work_ref, actor,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    if reuse:
        LOGGER.info("photo %s re-used from %s works", name, len(reuse))
    return {"fingerprinted": True, **fp.as_dict(), "reuse": reuse}


def record(work_ref: str, outcome: str, actor: str, role: str, notes: str = "",
           photo: str | None = None, ocr_text: str | None = None,
           demo: bool = False, board_ref: str | None = None,
           board_amount: float | None = None, ocr_confidence: float | None = None,
           needed_confirmation: bool = False, photo_reuse_count: int = 0,
           reused_from: str | None = None, ocr_engine: str | None = None,
           readers_agree: bool | None = None, document: str | None = None) -> dict:
    """Append one verification. Immutable once written.

    `demo` marks a record seeded for a demonstration. It is carried through to the API and
    shown in the interface, and excluded from the label count — a walkthrough must never
    inflate the number of real site visits.

    The `board_*` and `photo_*` arguments carry what the camera found, kept apart from what
    the officer concluded. A reference read off a board that disagrees with the work being
    verified, or a photograph already submitted for a different sanction, is evidence in its
    own right — and it is evidence about the *verification*, not about the work, which is
    exactly why it belongs on this record rather than folded into the outcome.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome}")
    ts = datetime.now(timezone.utc).isoformat()
    row_hash = hashlib.sha256(
        f"{work_ref}|{outcome}|{notes}|{photo}|{actor}|{ts}".encode()
    ).hexdigest()
    prints = _photo_hashes(photo)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO verification (work_ref, outcome, notes, photo, ocr_text, actor,"
            " role, created_at, row_hash, phash, dhash, demo, board_ref, board_amount,"
            " ocr_confidence, needed_confirmation, photo_reuse_count, reused_from,"
            " ocr_engine, readers_agree, document)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (work_ref, outcome, notes, photo, ocr_text, actor, role, ts, row_hash,
             prints.get("phash"), prints.get("dhash"), int(demo),
             board_ref, board_amount, ocr_confidence, int(needed_confirmation),
             int(photo_reuse_count), reused_from, ocr_engine,
             None if readers_agree is None else int(readers_agree), document),
        )
        conn.commit()
        new_id = cur.lastrowid
    LOGGER.info("verification %s recorded for %s by %s", outcome, work_ref, actor)
    return {"id": new_id, "work_ref": work_ref, "outcome": outcome, "created_at": ts,
            "row_hash": row_hash, "demo": demo,
            "board_ref": board_ref, "board_disagrees": bool(board_ref
                                                            and board_ref != work_ref),
            "photo_reuse_count": photo_reuse_count}


def _photo_hashes(photo: str | None) -> dict[str, str]:
    """The fingerprint already computed at upload, if this record carries a photo."""
    if not photo:
        return {}
    with _connect() as conn:
        row = conn.execute(
            "SELECT phash, dhash FROM photo WHERE name = ?", (photo,)
        ).fetchone()
    return dict(row) if row else {}


def for_work(work_ref: str) -> list[dict]:
    """Every verification for one work, newest first. History, not just the latest."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM verification WHERE work_ref = ? ORDER BY id DESC", (work_ref,)
        ).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM verification ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def label_readiness() -> dict:
    """How close the verification record is to being usable as training labels.

    Reported rather than assumed. Fitting signal weights to a handful of visits would
    overfit to whoever happened to go out first, so the threshold is stated openly.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT outcome, COUNT(*) n FROM verification WHERE demo = 0 GROUP BY outcome"
        ).fetchall()
        works = conn.execute(
            "SELECT COUNT(DISTINCT work_ref) n FROM verification WHERE demo = 0"
        ).fetchone()["n"]
        seeded = conn.execute(
            "SELECT COUNT(*) n FROM verification WHERE demo = 1"
        ).fetchone()["n"]
    counts = {r["outcome"]: r["n"] for r in rows}
    total = sum(counts.values())
    confirmed = sum(n for outcome, n in counts.items() if outcome in CONFIRMS_CONCERN)
    target = 500
    return {
        "verifications": total,
        "works_verified": works,
        "demo_records_excluded": seeded,
        "by_outcome": counts,
        "concerns_confirmed": confirmed,
        "labels_needed_to_fit_weights": max(0, target - total),
        "ready_to_fit": total >= target,
        "note": (
            "Verification outcomes are the only real ground truth this system can ever "
            f"obtain. At {target}+ records the fusion weights could be fitted to what "
            "officers actually confirmed, instead of the reasoned defaults in config.py. "
            f"Currently {total}. Until then nothing is refitted and no accuracy is claimed."
        ),
    }


def photo_reuse_report() -> dict:
    """Every photograph submitted for more than one work.

    The portfolio-level view of the same check `check_photo` runs at upload. It exists so
    the pattern is visible without anyone having to re-upload anything, and so a reviewer
    can see how rare it is — which is what makes an instance worth looking at.
    """
    with _connect() as conn:
        photos = [dict(r) for r in conn.execute(
            "SELECT v.photo, v.work_ref, v.actor, v.created_at, v.phash, v.dhash"
            " FROM verification v WHERE v.photo IS NOT NULL AND v.phash IS NOT NULL"
            " ORDER BY v.id"
        )]

    clusters: list[dict] = []
    for row in photos:
        for cluster in clusters:
            head = cluster["members"][0]
            match = photohash.verdict(
                photohash.distance(row["phash"], head["phash"]),
                photohash.distance(row["dhash"], head["dhash"]),
            )
            if match["match"]:
                cluster["members"].append(row)
                cluster["level"] = min(cluster["level"], match["level"],
                                       key=_LEVEL_ORDER.index)
                break
        else:
            clusters.append({"level": "IDENTICAL", "members": [row]})

    shared = [
        {
            "level": c["level"],
            "works": sorted({m["work_ref"] for m in c["members"]}),
            "submissions": len(c["members"]),
            "photo": c["members"][0]["photo"],
            "actors": sorted({m["actor"] for m in c["members"]}),
        }
        for c in clusters
        if len({m["work_ref"] for m in c["members"]}) > 1
    ]
    return {
        "photographs": len(photos),
        "shared_across_works": len(shared),
        "clusters": shared,
        "note": (
            "A photograph submitted for two different works is worth one question, not a "
            "conclusion. Two phases of the same road, or two sanctions at one school, "
            "legitimately look identical from the roadside."
        ),
    }


#: Worst-first, so `min(..., key=_LEVEL_ORDER.index)` keeps the strongest claim in a cluster.
_LEVEL_ORDER = ["IDENTICAL", "NEAR_IDENTICAL", "SAME_SCENE", "DIFFERENT"]


def photo_forensics_summary() -> dict:
    """What the camera evidence says across every verification recorded.

    Separated from `label_readiness` on purpose. Readiness counts labels; this counts
    *questions raised by photographs* — boards that disagreed with the record, matches the
    machine refused to settle, and pictures submitted more than once. None of them is a
    finding, and all of them are worth a person's attention.
    """
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT work_ref, board_ref, ocr_confidence, needed_confirmation,"
            " photo_reuse_count, reused_from, actor, created_at, demo"
            # The filter is on the evidence, not the file. A record can carry camera
            # evidence with no stored photograph — the upload can fail after the read
            # succeeds — and a re-used-photograph finding carries neither a board reference
            # nor, necessarily, a saved image, while being exactly the kind of question
            # this summary exists to count.
            " FROM verification WHERE photo IS NOT NULL OR board_ref IS NOT NULL"
            " OR photo_reuse_count > 0"
            " ORDER BY id DESC"
        )]

    disagreed = [r for r in rows if r["board_ref"] and r["board_ref"] != r["work_ref"]]
    unsettled = [r for r in rows if r["needed_confirmation"]]
    reused = [r for r in rows if (r["photo_reuse_count"] or 0) > 0]

    return {
        "photographs": len(rows),
        "board_disagreed_with_record": len(disagreed),
        "machine_refused_to_settle": len(unsettled),
        "photographs_seen_before": len(reused),
        "examples": [
            {"work_ref": r["work_ref"], "board_ref": r["board_ref"],
             "confidence": r["ocr_confidence"], "reused_from": r["reused_from"],
             "actor": r["actor"], "when": str(r["created_at"])[:10],
             "demonstration_record": bool(r["demo"])}
            for r in (disagreed + reused)[:10]
        ],
        "note": (
            "A board that disagrees with the record is usually a misread digit, not a "
            "misplaced work; MPLADS references run in sequence, so a single wrong "
            "character lands on a different real work. A photograph seen before is usually "
            "two phases of one site. Both are questions for a person, never conclusions."
        ),
    }
