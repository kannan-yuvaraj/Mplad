"""Tests for the intake assessment.

No OCR, no network. A fake reader and a fake portfolio drive the stage machine,
because what needs pinning is the *judgement* in each stage — when it blocks,
when it merely raises a question — not whether a third-party OCR engine works.
"""

from __future__ import annotations

import pytest

from mplads import submission
from mplads.submission import ATTENTION, BLOCKED, INFO, OK, Assessment

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

CASE = {
    "work_ref": "MP1-W100",
    "surfaced": True,
    "identity": {"state": "Bihar", "implementing_agency": "SARAN", "constituency": "SARAN"},
    "peer_context": {"level": "category", "group_size": 400, "amount_percentile": 0.999},
    "archetype": {"id": 3, "label": "school rooms"},
    "risk": {"completion_risk": 0.44, "basis": "cox"},
    "early_warning": {"level": "HIGH", "score": 0.7, "reason": "stalled"},
    "compliance_findings": ["completed without a sanction row"],
    "lifecycle": {"stage": "Completed", "days_open": 800},
    "duplicate": {"partner_work_ref": "MP1-W101", "similarity": 0.97,
                  "classification": "near-identical"},
    "confidence_band": "HIGH",
    "evidence": ["amount at the top of its peer group", "stalled well past peer median"],
    "n_signal_families": 4,
    "exposure_rupees": 6_500_000,
    "audit_roi": 120_000,
    "priority": 0.9,
    "recommended_next_step": "A human should verify the scope with the Implementing Agency.",
    "suggested_actions": ["Compare scope and estimate with peer works"],
    "disclaimer": "This system identifies patterns warranting human investigation; "
                  "it does not determine fraud.",
}


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    """An assessment whose uploads land in a tmp dir and whose reader is fake."""
    from mplads import field as field_mod

    monkeypatch.setattr(field_mod, "PHOTOS", tmp_path / "photos", raising=False)
    monkeypatch.setattr(field_mod, "DOCUMENTS", tmp_path / "docs", raising=False)
    (tmp_path / "photos").mkdir()
    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(submission.field, "save_photo",
                        lambda data, name: "stored.png")
    monkeypatch.setattr(submission.field, "save_document",
                        lambda data, name: "stored.pdf")
    monkeypatch.setattr(submission.field, "check_photo",
                        lambda data, name, ref, actor="": {"fingerprinted": True,
                                                           "phash": "a", "dhash": "b",
                                                           "reuse": []})
    monkeypatch.setattr(submission.ocr, "available", lambda: False)
    monkeypatch.setattr(submission.ocr, "documents_available", lambda: False)
    monkeypatch.setattr(submission.ocr, "status", lambda: {"engines": []})

    return Assessment(known_refs={"MP1-W100", "MP1-W101"},
                      amounts={"MP1-W100": 1_000_000.0},
                      case_lookup=lambda ref: CASE if ref == "MP1-W100" else None)


def stages(engine, **kwargs):
    kwargs.setdefault("data", PNG)
    kwargs.setdefault("filename", "board.png")
    kwargs.setdefault("kind", "photo")
    return {s.stage: s for s in engine.run(**kwargs)}


# --------------------------------------------------------------------------
# The identity guard — the safety-critical stage
# --------------------------------------------------------------------------

def test_a_disagreement_between_the_file_and_the_form_blocks(engine, monkeypatch):
    """MPLADS references run in sequence, so one misread digit is a different
    real work. The machine must narrow, never settle."""
    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read",
                        lambda p, **kw: {"lines": [], "fields": {"work_ref": {"value": "MP1-W101"}}})
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W101",
                                               "needs_confirmation": False,
                                               "alternatives": ["MP1-W100"]})

    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["identify"].status == BLOCKED
    assert "MP1-W101" in got["identify"].headline
    assert "MP1-W100" in got["identify"].headline
    assert got["identify"].detail["needs_confirmation"] is True


def test_a_blocked_identity_still_runs_the_remaining_checks(engine, monkeypatch):
    """Stopping at the disagreement would hide the photo re-use and the lead —
    the officer needs the whole picture to decide which work it belongs to."""
    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read",
                        lambda p, **kw: {"lines": [], "fields": {"work_ref": {"value": "MP1-W101"}}})
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W101",
                                               "needs_confirmation": False, "alternatives": []})

    got = stages(engine, declared_work_ref="MP1-W100")

    assert "lead" in got
    assert got["lead"].detail["band"] == "HIGH"


def test_an_unconfirmed_identity_is_carried_into_the_lead(engine):
    """The lead must say the identity was never confirmed, or a reader will
    assume the evidence below it is about the work they think it is."""
    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["identify"].status == ATTENTION
    assert any("not been confirmed" in n
               for n in got["lead"].detail["submission_notes"])


def test_an_unknown_reference_stops_rather_than_inventing_a_record(engine):
    got = stages(engine, declared_work_ref="MP9-W999")

    assert got["record"].status == BLOCKED
    assert "lead" not in got


def test_no_reference_at_all_stops_cleanly(engine):
    got = stages(engine, declared_work_ref="")

    assert got["identify"].status == BLOCKED
    assert "lead" not in got


# --------------------------------------------------------------------------
# It degrades rather than failing
# --------------------------------------------------------------------------

def test_the_assessment_runs_with_no_ocr_installed(engine):
    """A demo must not die because a reader is cold. Every stage after identity
    works from the reference, however it was obtained."""
    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["read"].status == INFO
    assert "typed reference" in got["read"].headline
    assert got["lead"].detail["band"] == "HIGH"


def test_a_reader_that_throws_does_not_end_the_assessment(engine, monkeypatch):
    monkeypatch.setattr(submission.ocr, "available", lambda: True)

    def boom(_path, **kw):
        raise RuntimeError("model not loaded")

    monkeypatch.setattr(submission.ocr, "read", boom)
    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["read"].status == INFO
    assert "lead" in got


# --------------------------------------------------------------------------
# The checks themselves
# --------------------------------------------------------------------------

def test_an_amount_matching_the_record_is_not_raised(engine):
    got = stages(engine, declared_work_ref="MP1-W100", declared_amount=1_000_000.0)
    assert got["cross_check"].status == OK


def test_an_amount_disagreeing_with_the_record_is_raised(engine):
    got = stages(engine, declared_work_ref="MP1-W100", declared_amount=2_500_000.0)

    assert got["cross_check"].status == ATTENTION
    assert got["cross_check"].detail["difference"] == 1_500_000.0


def test_a_reused_photograph_is_a_question_not_a_finding(engine, monkeypatch):
    monkeypatch.setattr(submission.field, "check_photo",
                        lambda data, name, ref, actor="": {
                            "fingerprinted": True, "phash": "a", "dhash": "b",
                            "reuse": [{"work_ref": "MP1-W101", "first_seen": "2026-01-01",
                                       "exact_file": False}]})

    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["photo_forensics"].status == ATTENTION
    assert "MP1-W101" in got["photo_forensics"].headline
    # Never a conclusion.
    explain = got["photo_forensics"].explain.lower()
    assert "question" in explain and "never concluded" in explain


def test_the_same_work_photographed_twice_is_not_flagged(engine):
    """`check_photo` only reports re-use across different works, and this stage
    must say so — otherwise an officer revisiting a site looks suspicious."""
    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["photo_forensics"].status == OK
    assert "different" in got["photo_forensics"].explain


def test_a_clear_record_is_reported_as_clear_not_as_low_risk(engine):
    """173,288 works were never surfaced. Presenting them as 'low risk' would
    imply they were assessed and passed."""
    clear = dict(CASE, surfaced=False, confidence_band=None, evidence=[],
                 n_signal_families=0)
    engine.case_lookup = lambda ref: clear

    got = stages(engine, declared_work_ref="MP1-W100")

    assert got["lead"].status == INFO
    assert "Clear record" in got["lead"].headline


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------

def test_every_stage_carries_an_explanation(engine):
    """A judge asking 'why does that check exist?' must get an answer from the
    screen, not from the person demoing it."""
    for stage in stages(engine, declared_work_ref="MP1-W100").values():
        assert stage.explain.strip(), f"{stage.stage} has no explanation"
        assert len(stage.explain) > 40


def test_the_lead_never_claims_a_fraud_finding(engine):
    got = stages(engine, declared_work_ref="MP1-W100")
    lead = got["lead"]

    assert lead.detail["not_a_fraud_finding"] is True
    assert "fraud" not in lead.headline.lower()
    assert "does not determine fraud" in (lead.detail["disclaimer"] or "")


def test_the_lead_ends_in_something_a_human_should_do(engine):
    got = stages(engine, declared_work_ref="MP1-W100")
    assert got["lead"].detail["recommended_next_step"].startswith("A human should")


def test_the_silhouette_caveat_survives_into_the_peer_stage(engine):
    """Constraint 3: silhouette is not accuracy, and it must be said wherever the
    clustering is used — including here."""
    got = stages(engine, declared_work_ref="MP1-W100")
    assert "0.050" in got["peer"].explain
    assert "not accuracy" in got["peer"].explain


def test_the_stage_plan_matches_what_actually_runs(engine):
    """The UI draws the plan before anything resolves. If a stage ran that was
    not in the plan, its row would never appear."""
    planned = {name for name, _ in submission.STAGE_PLAN}
    ran = set(stages(engine, declared_work_ref="MP1-W100"))

    assert ran <= planned, f"stages ran that the plan does not list: {ran - planned}"


def test_stages_are_numbered_in_order(engine):
    orders = [s.order for s in stages(engine, declared_work_ref="MP1-W100").values()]
    assert orders == sorted(orders)
    assert orders[0] == 1


# --------------------------------------------------------------------------
# Choosing the fast reader
# --------------------------------------------------------------------------

def test_choosing_the_fast_reader_turns_off_the_second_reader(engine, monkeypatch):
    """`ocr.read` cross-checks with the *other* engine. Asking for the fast
    reader while leaving that on would still invoke the slow one and save
    nothing — which was the bug this test exists to stop coming back."""
    seen = {}

    def fake_read(path, **kw):
        seen.update(kw)
        return {"lines": [], "fields": {"work_ref": {"value": "MP1-W100"}},
                "engine": "rapidocr", "seconds": 1.9}

    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read", fake_read)
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W100",
                                               "needs_confirmation": False, "alternatives": []})

    got = stages(engine, declared_work_ref="MP1-W100", reader="rapidocr")

    assert seen["prefer"] == "rapidocr"
    assert seen["cross_check"] is False
    assert got["read"].detail["second_reader_ran"] is False


def test_the_accurate_reader_keeps_its_second_reader(engine, monkeypatch):
    seen = {}

    def fake_read(path, **kw):
        seen.update(kw)
        return {"lines": [], "fields": {"work_ref": {"value": "MP1-W100"}},
                "engine": "surya", "seconds": 7.0}

    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read", fake_read)
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W100",
                                               "needs_confirmation": False, "alternatives": []})

    got = stages(engine, declared_work_ref="MP1-W100", reader="surya")

    assert seen["cross_check"] is True
    assert got["read"].detail["second_reader_ran"] is True


def test_a_single_reader_never_implies_two_readers_agreed(engine, monkeypatch):
    """With one reader there is no independent reading, and the stage must say
    so — otherwise a judge reads 'identified' as corroborated."""
    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read",
                        lambda p, **kw: {"lines": [], "fields": {"work_ref": {"value": "MP1-W100"}},
                                         "engine": "rapidocr", "seconds": 1.9})
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W100",
                                               "needs_confirmation": False, "alternatives": []})

    got = stages(engine, declared_work_ref="MP1-W100", reader="rapidocr")

    assert "no second reading to disagree" in got["read"].explain


def test_an_unknown_reader_name_does_not_lose_the_read(engine, monkeypatch):
    """A preference is a preference. Losing the read because a named engine is
    missing would be the worse failure."""
    monkeypatch.setattr(submission.ocr, "available", lambda: True)
    monkeypatch.setattr(submission.ocr, "read",
                        lambda p, **kw: {"lines": [], "fields": {"work_ref": {"value": "MP1-W100"}},
                                         "engine": "surya", "seconds": 7.0})
    monkeypatch.setattr(submission.ocr, "match_to_work",
                        lambda e, refs, amts: {"matched": True, "work_ref": "MP1-W100",
                                               "needs_confirmation": False, "alternatives": []})

    got = stages(engine, declared_work_ref="MP1-W100", reader="nonexistent-engine")

    assert got["read"].status == OK
    assert "lead" in got
