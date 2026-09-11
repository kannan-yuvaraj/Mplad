"""Photo reading and field verification.

Two things are worth proving here and nothing else is. First, that the OCR layer is
*honest* — it degrades to manual entry instead of failing, and every field it hands back
carries the text it came from so an officer can see what was read. Second, that a
verification record cannot be changed after the fact, because a record an auditor could
quietly edit is not evidence.
"""

from __future__ import annotations

import sqlite3

import pytest

from mplads import field, ocr


# ------------------------------------------------------------------------- ocr


@pytest.mark.parametrize(
    "text, expected",
    [
        ("MP3018356-W86316", "MP3018356-W86316"),
        ("MP 3018356 - W 86316", "MP3018356-W86316"),
        ("mp3018356–w86316", "MP3018356-W86316"),          # en-dash, lower case
        ("Work No. MP3O18356-W863I6 (board)", "MP3018356-W86316"),  # O/I confusion
    ],
)
def test_work_reference_survives_the_way_a_camera_reads_it(text, expected):
    match = ocr.WORK_REF.search(text)
    assert match is not None, f"no reference found in {text!r}"
    assert ocr._normalise_ref(match.group(1), match.group(2)) == expected


def test_a_line_with_no_reference_yields_nothing():
    assert ocr.WORK_REF.search("Outdoor gym, Saran district") is None


@pytest.mark.parametrize(
    "raw, unit, expected",
    [
        ("6,50,00,000", None, 65_000_000.0),
        ("6.5", "Cr", 65_000_000.0),
        ("650", "lakh", 65_000_000.0),
        ("650", "lac", 65_000_000.0),
        ("65000", None, 65_000.0),
    ],
)
def test_amounts_are_read_in_the_units_indian_boards_actually_use(raw, unit, expected):
    assert ocr._parse_amount(raw, unit) == expected


def test_an_unparseable_amount_is_dropped_rather_than_guessed():
    assert ocr._parse_amount("six lakh", None) is None


def test_reading_degrades_to_manual_entry_when_no_engine_is_installed(monkeypatch, tmp_path):
    """A machine without the OCR runtime must still be able to record a verification."""
    monkeypatch.setattr(ocr, "_engine", lambda: None)
    result = ocr.read(tmp_path / "nothing.png")
    assert result["available"] is False
    assert result["fields"] == {}
    assert "manually" in result["note"]


def test_a_reference_we_do_not_hold_is_reported_as_such_not_silently_matched():
    extracted = {"fields": {"work_ref": {"value": "MP9999999-W99999", "confidence": 0.9}}}
    verdict = ocr.match_to_work(extracted, {"MP3018356-W86316"})
    assert verdict["matched"] is False
    assert verdict["work_ref"] == "MP9999999-W99999"
    assert "not a work in this dataset" in verdict["reason"]


def test_a_reference_we_hold_matches():
    extracted = {"fields": {"work_ref": {"value": "MP3018356-W86316", "confidence": 0.98}}}
    verdict = ocr.match_to_work(extracted, {"MP3018356-W86316"})
    assert verdict["matched"] is True
    assert verdict["confidence"] == 0.98


def test_no_reference_in_the_image_is_not_a_match():
    assert ocr.match_to_work({"fields": {}}, {"MP3018356-W86316"})["matched"] is False


@pytest.mark.skipif(not ocr.ENGINES["rapidocr"].available(),
                    reason="RapidOCR runtime not installed on this machine")
def test_the_engine_reads_a_rendered_work_board_end_to_end(tmp_path, monkeypatch):
    """Exercises the real RapidOCR runtime. Pinned to it so the default test run does not
    start Surya's model server; tests/test_ocr_real.py covers Surya and Docling for real."""
    from PIL import Image, ImageDraw

    monkeypatch.setattr(ocr.config, "OCR_IMAGE_ENGINES", ("rapidocr",))

    board = Image.new("RGB", (900, 320), "white")
    draw = ImageDraw.Draw(board)
    for i, line in enumerate([
        "MPLADS WORK BOARD",
        "Work No. MP3018356-W86316",
        "Sanctioned Amount Rs 6,50,00,000",
        "District Planning Office, Saran",
    ]):
        draw.text((40, 40 + i * 60), line, fill="black")
    path = tmp_path / "board.png"
    board.save(path)

    result = ocr.read(path)
    assert result["available"] is True
    assert result["lines"], "engine returned no text at all"
    assert result["fields"]["work_ref"]["value"] == "MP3018356-W86316"
    # Every field carries the text it was read from, so the officer can check it.
    assert "source_text" in result["fields"]["work_ref"]


# ----------------------------------------------------------------------- field


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(field, "DB", tmp_path / "verifications.sqlite")
    monkeypatch.setattr(field, "PHOTOS", tmp_path / "photos")
    return field


def test_a_verification_round_trips(store):
    store.record("MP1-W1", "NOT_STARTED", actor="auditor", role="auditor",
                 notes="Nothing at the site.")
    history = store.for_work("MP1-W1")
    assert len(history) == 1
    assert history[0]["outcome"] == "NOT_STARTED"
    assert history[0]["actor"] == "auditor"
    assert history[0]["row_hash"]


def test_history_is_kept_not_overwritten(store):
    """A later visit supersedes an earlier one; it does not erase it."""
    store.record("MP1-W1", "NOT_STARTED", actor="a", role="auditor")
    store.record("MP1-W1", "VERIFIED_IN_PROGRESS", actor="b", role="state")
    history = store.for_work("MP1-W1")
    assert [h["outcome"] for h in history] == ["VERIFIED_IN_PROGRESS", "NOT_STARTED"]


def test_a_recorded_verification_cannot_be_edited(store):
    store.record("MP1-W1", "NOT_FOUND", actor="auditor", role="auditor")
    with sqlite3.connect(store.DB) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE verification SET outcome = 'VERIFIED_COMPLETE'")


def test_a_recorded_verification_cannot_be_deleted(store):
    store.record("MP1-W1", "NOT_FOUND", actor="auditor", role="auditor")
    with sqlite3.connect(store.DB) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM verification")


def test_an_invented_outcome_is_refused(store):
    with pytest.raises(ValueError, match="unknown outcome"):
        store.record("MP1-W1", "DEFINITELY_A_PROBLEM", actor="a", role="auditor")


def test_every_outcome_the_ui_offers_is_accepted(store):
    for outcome in field.OUTCOMES:
        store.record("MP1-W1", outcome, actor="a", role="auditor")
    assert len(store.for_work("MP1-W1")) == len(field.OUTCOMES)


def test_outcomes_include_ones_that_clear_a_work():
    """A verification tool that can only confirm suspicion is a tool for confirming it."""
    assert "VERIFIED_COMPLETE" in field.OUTCOMES
    assert field.CONFIRMS_CONCERN < set(field.OUTCOMES)
    assert "VERIFIED_COMPLETE" not in field.CONFIRMS_CONCERN


def test_the_same_photograph_is_stored_once(store):
    first = store.save_photo(b"\x89PNG-pretend", "IMG_0001.png")
    second = store.save_photo(b"\x89PNG-pretend", "a-different-name.png")
    assert first == second
    assert len(list(store.PHOTOS.iterdir())) == 1


def test_a_non_image_upload_is_refused(store):
    with pytest.raises(ValueError, match="unsupported image type"):
        store.save_photo(b"MZ", "payload.exe")


def test_readiness_reports_the_gap_instead_of_claiming_it_is_closed(store):
    empty = store.label_readiness()
    assert empty["verifications"] == 0
    assert empty["ready_to_fit"] is False

    store.record("MP1-W1", "NOT_STARTED", actor="a", role="auditor")
    store.record("MP2-W2", "VERIFIED_COMPLETE", actor="a", role="auditor")
    after = store.label_readiness()
    assert after["verifications"] == 2
    assert after["works_verified"] == 2
    assert after["concerns_confirmed"] == 1     # VERIFIED_COMPLETE is not a concern
    assert after["labels_needed_to_fit_weights"] == 498
    assert after["ready_to_fit"] is False
    assert "no accuracy is claimed" in after["note"]


# ------------------------------------------------- camera evidence on a verification


def test_what_the_camera_read_is_stored_apart_from_what_was_verified(store):
    """The two disagreeing is the most useful thing a photograph can report.

    A weathered board reads one digit wrong at 99.6% confidence and lands on a *different
    real work*, because MPLADS references run in sequence. Storing only the resolved
    answer throws away the one signal that says "check this match".
    """
    store.record("MP3017167-W136962", "RECORD_MISMATCH", actor="r.sharma", role="auditor",
                 board_ref="MP3017167-W136963", ocr_confidence=0.996,
                 needed_confirmation=True)
    row = store.for_work("MP3017167-W136962")[0]
    assert row["board_ref"] == "MP3017167-W136963"
    assert row["work_ref"] != row["board_ref"]
    assert row["needed_confirmation"] == 1


def test_a_record_reports_whether_its_board_disagreed(store):
    disagreed = store.record("MP1-W1", "RECORD_MISMATCH", actor="a", role="auditor",
                             board_ref="MP1-W2")
    agreed = store.record("MP1-W1", "VERIFIED_COMPLETE", actor="a", role="auditor",
                          board_ref="MP1-W1")
    assert disagreed["board_disagrees"] is True
    assert agreed["board_disagrees"] is False


def test_photo_reuse_travels_with_the_verification(store):
    store.record("MP2-W2", "VERIFIED_COMPLETE", actor="a", role="auditor",
                 photo_reuse_count=2, reused_from="MP9-W9")
    row = store.for_work("MP2-W2")[0]
    assert row["photo_reuse_count"] == 2
    assert row["reused_from"] == "MP9-W9"


def test_forensics_counts_questions_not_findings(store):
    store.record("MP1-W1", "RECORD_MISMATCH", actor="a", role="auditor",
                 board_ref="MP1-W9", needed_confirmation=True)
    store.record("MP2-W2", "VERIFIED_COMPLETE", actor="a", role="auditor",
                 photo_reuse_count=1, reused_from="MP1-W1")
    store.record("MP3-W3", "VERIFIED_COMPLETE", actor="a", role="auditor")

    summary = store.photo_forensics_summary()
    assert summary["board_disagreed_with_record"] == 1
    assert summary["machine_refused_to_settle"] == 1
    assert summary["photographs_seen_before"] == 1
    # The record with no camera evidence is not counted as a question.
    assert summary["photographs"] == 2
    assert "questions for a person, never conclusions" in summary["note"]


def test_camera_evidence_is_optional(store):
    """Most verifications are typed, not photographed, and must still record."""
    store.record("MP4-W4", "NOT_STARTED", actor="a", role="auditor")
    row = store.for_work("MP4-W4")[0]
    assert row["board_ref"] is None
    assert row["photo_reuse_count"] == 0
