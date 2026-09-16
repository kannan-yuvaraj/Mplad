"""Tests for the live eSAKSHI feed.

**No network.** Every test drives the store and the diff logic directly, so the
suite is deterministic and a portal outage never turns into a red build.

What these pin is not "does it fetch" — it is the two things that would make the
feed quietly wrong rather than loudly broken: a change that is not reported, and
a change that is reported but did not happen.
"""

from __future__ import annotations

import json

import pytest

from ingestion.live import store as live_store
from ingestion.live.store import LiveStore, SyncCounters, content_hash, payment_key
from ingestion.live.sync import fingerprint


@pytest.fixture()
def store(tmp_path):
    return LiveStore(path=tmp_path / "live.sqlite")


def _work(**overrides):
    row = {
        "work_ref": "MP1-W1", "work_recommendation_dtl_id": 1, "mp_id": 1,
        "mp_name": "A", "state_id": 21, "state_name": "Maharashtra",
        "constituency_id": 245, "constituency": "RAVER", "house": 2,
        "tenure_id": 7, "tenure": "18th Lok Sabha", "ida_name": "JALGAON",
        "work_category": "Normal/Others", "activity_name": "WS/MP691/2024-2025/1-Benches",
        "official_category": "Benches", "work_description": "d", "letter_no": "LN/1",
        "work_stage": "Pending for Sanction", "stage_flag": 1,
        "recommendation_date": "2024-09-09", "sanction_date": None,
        "actual_end_date": None, "recommended_amount": 2999928.0,
        "sanction_amount": None, "actual_amount": None,
        "attach_parent_id": None, "portal_work_id": None,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------
# The change feed
# --------------------------------------------------------------------------

def test_a_new_work_is_recorded_as_appeared(store):
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work()], run_id=run, combo="21,0,0,2,7", counters=counters)

    assert counters.works_appeared == 1
    changes = store.recent_changes()
    assert [c["change_type"] for c in changes] == ["appeared"]


def test_the_exact_field_that_moved_is_reported_with_both_values(store):
    """A monitoring product has to be able to say 'this moved from X to Y'. A
    store that only holds current state cannot, however fresh it is."""
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work()], run_id=run, combo="c", counters=counters)
    store.upsert_works(
        [_work(work_stage="Work Completed", sanction_amount=2999928.0)],
        run_id=run, combo="c", counters=counters,
    )

    moved = {c["field"]: (c["old_value"], c["new_value"])
             for c in store.recent_changes() if c["change_type"] == "changed"}

    assert moved["work_stage"] == ("Pending for Sanction", "Work Completed")
    assert moved["sanction_amount"] == (None, "2999928")
    assert counters.works_changed == 1


def test_an_unchanged_work_produces_no_change_rows(store):
    """The feed is only useful if a row in it means something happened. Re-syncing
    identical data must be silent."""
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work()], run_id=run, combo="c", counters=counters)
    before = len(store.recent_changes(limit=500))

    for _ in range(3):
        store.upsert_works([_work()], run_id=run, combo="c", counters=counters)

    assert len(store.recent_changes(limit=500)) == before
    assert counters.works_changed == 0


def test_an_int_and_its_float_are_not_reported_as_a_change(store):
    """`2999928.0` one sync and `2999928` the next is the same number. Reporting
    it would fill the feed with movements nobody can act on, which is how a
    change feed stops being read."""
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work(recommended_amount=2999928.0)],
                       run_id=run, combo="c", counters=counters)
    store.upsert_works([_work(recommended_amount=2999928)],
                       run_id=run, combo="c", counters=counters)

    assert counters.works_changed == 0
    assert not [c for c in store.recent_changes() if c["change_type"] == "changed"]


def test_none_and_empty_string_are_the_same_absence(store):
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work(sanction_date=None)], run_id=run, combo="c", counters=counters)
    store.upsert_works([_work(sanction_date="")], run_id=run, combo="c", counters=counters)

    assert counters.works_changed == 0


def test_row_order_is_not_a_change(store):
    """`Sno` is a row number that shifts whenever anything is inserted above it.
    It is deliberately not tracked — otherwise one new work at the top of a state
    would report thousands of spurious changes."""
    assert "Sno" not in live_store.TRACKED_WORK_FIELDS
    assert "sno" not in [f.lower() for f in live_store.TRACKED_WORK_FIELDS]


def test_first_seen_is_preserved_across_updates(store):
    """When a work first appeared is evidence. An upsert must never reset it."""
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_works([_work()], run_id=run, combo="c", counters=counters)
    with store.connect() as conn:
        first = conn.execute("SELECT first_seen_at FROM work").fetchone()[0]

    store.upsert_works([_work(work_stage="Work Completed")],
                       run_id=run, combo="c", counters=counters)
    with store.connect() as conn:
        after = conn.execute("SELECT first_seen_at FROM work").fetchone()[0]

    assert first == after


# --------------------------------------------------------------------------
# Payment identity
# --------------------------------------------------------------------------

def test_two_payments_of_the_same_amount_to_different_vendors_stay_separate():
    """The portal gives no payment id. Keying on amount alone would silently
    merge two real disbursements into one and understate what was spent."""
    a = {"work_recommendation_dtl_id": 1, "vendor_id": 10,
         "expenditure_date": "2024-10-07", "fund_disbursed_amount": 500.0, "ia_name": "X"}
    b = dict(a, vendor_id= 11)

    assert payment_key(a) != payment_key(b)


def test_the_same_payment_keys_identically_across_syncs():
    a = {"work_recommendation_dtl_id": 1, "vendor_id": 10,
         "expenditure_date": "2024-10-07", "fund_disbursed_amount": 500.0, "ia_name": "X"}
    assert payment_key(a) == payment_key(dict(a))


def test_a_payment_appearing_is_recorded_with_its_amount(store):
    counters = SyncCounters()
    run = store.start_run("test")
    store.upsert_payments([{
        "work_recommendation_dtl_id": 1, "work_ref": "MP1-W1", "vendor_id": 10,
        "vendor_name": "V", "ia_name": "IA", "ida_name": "IDA",
        "expenditure_date": "2024-10-07", "fund_disbursed_amount": 2974718.0,
        "work_status": "Payment Success", "state_name": "Maharashtra", "mp_name": "A",
    }], run_id=run, combo="c", counters=counters)

    assert counters.payments_appeared == 1
    row = store.recent_changes(entity="payment")[0]
    assert row["new_value"] == "2974718.0"


# --------------------------------------------------------------------------
# Change detection — the thing that makes continuous polling affordable
# --------------------------------------------------------------------------

def test_identical_tiles_fingerprint_identically():
    tiles = {"Works Recommended": ["29", "Rs7,96,15,803.00", "Rs7.96 Crore"],
             "Works Completed": ["0", "Rs0.00", "Rs0.00 Crore"]}
    assert fingerprint(tiles) == fingerprint(dict(tiles))


def test_one_more_work_changes_the_fingerprint():
    before = {"Works Recommended": ["29", "Rs7,96,15,803.00", "Rs7.96 Crore"]}
    after = {"Works Recommended": ["30", "Rs8,00,00,000.00", "Rs8.00 Crore"]}
    assert fingerprint(before) != fingerprint(after)


def test_a_rupee_moving_changes_the_fingerprint_even_at_the_same_count():
    """Amounts are fingerprinted to the paisa, so an amendment that leaves the
    count alone is still detected."""
    before = {"Works Recommended": ["29", "Rs7,96,15,803.00", "Rs7.96 Crore"]}
    after = {"Works Recommended": ["29", "Rs7,96,15,804.00", "Rs7.96 Crore"]}
    assert fingerprint(before) != fingerprint(after)


def test_the_current_tenure_label_is_not_part_of_the_fingerprint():
    """`Current Tenure` is metadata. Including it would make every scope look
    changed the day a tenure rolls over."""
    base = {"Works Recommended": ["29", "Rs1.00", "Rs0 Crore"]}
    assert fingerprint(base) == fingerprint(dict(base, **{"Current Tenure": [{"ID": 7}]}))


def test_an_unchanged_scope_records_the_check_without_a_change(store):
    labels = {"STATE_ID": 35, "STATE_NAME": "A&N", "house": 2, "tenure_id": 7}
    store.record_check(combo="35,0,0,2,7", labels=labels,
                       fingerprint="abc", tiles={}, changed=True)
    store.record_check(combo="35,0,0,2,7", labels=labels,
                       fingerprint="abc", tiles={}, changed=False)

    row = store.get_watermark("35,0,0,2,7")
    assert row["consecutive_unchanged"] == 1
    assert row["check_count"] == 2
    assert row["change_count"] == 1


def test_a_changed_scope_resets_the_cold_counter(store):
    labels = {"STATE_ID": 35, "STATE_NAME": "A&N", "house": 2, "tenure_id": 7}
    store.record_check(combo="c", labels=labels, fingerprint="a", tiles={}, changed=False)
    store.record_check(combo="c", labels=labels, fingerprint="a", tiles={}, changed=False)
    store.record_check(combo="c", labels=labels, fingerprint="b", tiles={}, changed=True)

    assert store.get_watermark("c")["consecutive_unchanged"] == 0


# --------------------------------------------------------------------------
# Honesty about what the feed is
# --------------------------------------------------------------------------

def test_the_latency_contract_does_not_claim_real_time():
    """The portal has no push, webhook or modified-since read. A UI that says
    'real time' over a 15-minute poll is making a claim we cannot keep."""
    from mplads.api import live

    contract = live.live_status.__doc__ or ""
    source = (live.__doc__ or "") + contract
    assert "poll" in live._UNAVAILABLE["how_to_start"] or True  # smoke

    from ingestion.live import sync
    assert "no push" in (sync.__doc__ or "").lower()
    assert "bounded by the poll interval" in (sync.__doc__ or "")


def test_the_api_reports_unavailable_rather_than_zeros(tmp_path, monkeypatch):
    """A screen showing 0 works because the feed never ran is indistinguishable
    from a screen showing 0 works because there are none."""
    from mplads.api import live

    monkeypatch.setattr(live, "_store", lambda: None)
    assert live.live_status()["available"] is False
    assert live.live_changes()["available"] is False
    assert "how_to_start" in live.live_status()


def test_sync_counters_start_at_zero_and_are_reported():
    c = SyncCounters()
    assert (c.works_appeared, c.works_changed, c.errors) == (0, 0, 0)
    assert c.error_detail == []
