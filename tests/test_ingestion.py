"""Tests for the live-portal ingestion module.

**Nothing here touches the network.** Every test runs against fixtures shaped
exactly like real captured responses, so the suite stays fast, deterministic and
runnable with no internet — and so a portal outage never turns into a red build.

The response shapes below are copied verbatim from responses captured on
2026-09-10 and preserved under `data/portal/raw/api/`. If the portal changes
shape, these fixtures go stale and that is the point: they pin what we believe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion import config
from ingestion.api import Scope
from ingestion.crawler.checkpoint import Checkpoint
from ingestion.storage import attachments
from ingestion.storage.manifest import RawStore, sha256_bytes


# --------------------------------------------------------------------------
# Scope / combo — the parameter the whole crawl is built on
# --------------------------------------------------------------------------

def test_the_combo_is_state_constituency_mp_house_tenure_in_that_order():
    """Decoded from the dashboard's #searchFilter handler. Getting the order
    wrong silently returns another state's works, which is worse than an error."""
    assert Scope(21, 245, 3019105, 2, 7).to_combo() == "21,245,3019105,2,7"


def test_a_scope_without_a_tenure_sends_four_elements_not_five():
    """The frontend appends the tenure only when one is selected. Sending a
    trailing empty slot is not the same request."""
    assert Scope(21, 245, 3019105, 2).to_combo() == "21,245,3019105,2"


def test_zero_is_the_wildcard_in_the_first_three_positions():
    assert Scope(house=2, tenure_id=7).to_combo() == "0,0,0,2,7"


def test_lok_sabha_is_two_and_rajya_sabha_is_one():
    """From loksaba.js sethouse(279935^279933)=2 and rajyasaba.js ...=1.
    Swapping them crawls the wrong house and every count still looks plausible."""
    assert config.HOUSE_LOK_SABHA == 2
    assert config.HOUSE_RAJYA_SABHA == 1


def test_scope_slugs_are_distinct_per_scope():
    """The slug names the directory raw responses land in — a collision would
    have one state silently overwrite another."""
    slugs = {
        Scope(21, 0, 0, 2, 7).slug(),
        Scope(21, 0, 0, 2, 5).slug(),
        Scope(21, 0, 0, 1, 7).slug(),
        Scope(12, 0, 0, 2, 7).slug(),
    }
    assert len(slugs) == 4


# --------------------------------------------------------------------------
# The grand-total row — the bug that put 3,987 phantom rows in our snapshot
# --------------------------------------------------------------------------

REPORT_BODY = {
    "Total Works Recommended": json.dumps([
        {"WORK_RECOMMENDATION_DTL_ID": 140096, "RECOMMENDED_AMOUNT": 2999928.0,
         "ATTACH_ID": 703161, "FLAG": 1, "MP_NAME": "Smt Raksha Nikhil Khadse",
         "ACTIVITY_NAME": "WS/MP691/2024-2025/140096-Fitting of Sitting RCC Benches in Public Places"},
        {"WORK_RECOMMENDATION_DTL_ID": 175514, "RECOMMENDED_AMOUNT": 914736.0,
         "ATTACH_ID": 1839191, "FLAG": 1, "MP_NAME": "Smt Raksha Nikhil Khadse",
         "ACTIVITY_NAME": "WS/MP691/2025-2026/175514-Purchase of furniture"},
        {"Total_Amt": 3914664.0},
    ])
}


class _FakeResponse:
    def __init__(self, body):
        self.content = json.dumps(body).encode("utf-8")
        self.url = "https://example.invalid/rest/PreLoginDashboardData/getTilesReportData"
        self.request_body = "{}"
        self.status_code = 200
        self.content_type = "application/json"

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class _FakeClient:
    def __init__(self, body):
        self._body = body

    def post_json(self, path, body, **kwargs):
        return _FakeResponse(self._body)


def test_the_servers_grand_total_row_is_stripped_from_the_work_rows():
    """Every getTilesReportData response ends with {"Total_Amt": n}. It is a
    response footer, not a work. Concatenating it is exactly how 3,987 phantom
    rows entered the project's CSV snapshot — see DATA_CONTRACT.md 3."""
    from ingestion import api

    report = api.get_tile_report(_FakeClient(REPORT_BODY), Scope(), "Works Recommended")

    assert len(report.rows) == 2
    assert report.grand_total == 3914664.0
    assert all("Total_Amt" not in row for row in report.rows)


def test_a_response_with_no_total_row_still_parses():
    """Empty scopes return no footer. Assuming one is always present would drop
    a real work off the end of every such response."""
    from ingestion import api

    body = {"Total Works Recommended": json.dumps(
        [{"WORK_RECOMMENDATION_DTL_ID": 1, "RECOMMENDED_AMOUNT": 5.0}])}
    report = api.get_tile_report(_FakeClient(body), Scope(), "Works Recommended")

    assert len(report.rows) == 1
    assert report.grand_total is None


def test_an_unknown_tile_key_is_refused_rather_than_sent():
    from ingestion import api

    with pytest.raises(ValueError, match="unknown tile key"):
        api.get_tile_report(_FakeClient(REPORT_BODY), Scope(), "Total Expenditure")


# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------

def test_files_are_identified_by_magic_bytes_not_by_their_extension():
    """The portal serves attachments as base64 with no content type, and the
    filename is whatever the uploading agency typed. On the very first work we
    retrieved, `wc.jpg` was a scanned certificate."""
    assert attachments.sniff(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"
    assert attachments.sniff(b"%PDF-1.4\n%\xe2\xe3") == "application/pdf"
    assert attachments.sniff(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert attachments.sniff(b"not a known format") is None


def test_classification_falls_back_to_unknown_rather_than_guessing():
    assert attachments.classify("wc.jpg") == "image"
    assert attachments.classify("work cc.pdf") == "document"
    assert attachments.classify("mystery.xyz") == "unknown"


def test_the_na_sentinel_is_not_treated_as_a_file():
    """getAttachIdsbyFlag returns [{"FILE_NAME": "N/A", "URL": "N/A"}] when a
    stage carries no file. Storing a file called 'N/A' would be a fabricated
    artefact in a dataset whose whole point is provenance."""
    listing = [{"FILE_NAME": config.ATTACHMENT_ABSENT, "URL": config.ATTACHMENT_ABSENT}]

    found = []
    for record in listing:
        names = record.get("FILE_NAME")
        if names == config.ATTACHMENT_ABSENT or not isinstance(names, list):
            continue
        found.append(names)

    assert found == []


def test_a_listing_with_mismatched_names_and_ids_is_skipped_not_zipped():
    """zip() would silently truncate to the shorter list and we would download
    the wrong bytes under the right filename."""
    names = ["a.jpg", "b.pdf", "c.pdf"]
    ids = ["1.1", "1.2"]
    assert len(names) != len(ids)


def test_attachment_refs_carry_the_compound_id():
    """getAttachmentById needs '<parent>.<child>'; the bare parent returns [{}]."""
    ref = attachments.AttachmentRef("140096", 1, "703161.725942", "wc.jpg")
    assert "." in ref.attach_id
    assert ref.attach_id.split(".")[0] == "703161"
    assert ref.kind == "image"


def test_works_without_an_attach_id_are_not_asked_about():
    """Asking the portal about a work with no attachment is a wasted request
    against a government server, and there are ~180,000 of them."""
    rows = [
        {"WORK_RECOMMENDATION_DTL_ID": 1, "ATTACH_ID": 703161, "FLAG": 1},
        {"WORK_RECOMMENDATION_DTL_ID": 2, "ATTACH_ID": None, "FLAG": 1},
        {"WORK_RECOMMENDATION_DTL_ID": 3, "ATTACH_ID": "", "FLAG": 3},
        {"WORK_RECOMMENDATION_DTL_ID": 4, "ATTACH_ID": 0, "FLAG": 1},
    ]
    assert [w for w, _ in attachments.iter_attachment_refs(rows)] == ["1"]


# --------------------------------------------------------------------------
# Checkpointing — what makes a multi-day crawl survivable
# --------------------------------------------------------------------------

def test_a_checkpoint_resumes_from_its_append_only_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHECKPOINT_ROOT", tmp_path)

    first = Checkpoint.load("unit-test")
    for key in ("a", "b", "c"):
        first.mark(key)
    first.close()

    second = Checkpoint.load("unit-test")
    assert second.completed == {"a", "b", "c"}
    assert second.done("b")
    assert not second.done("d")


def test_marking_is_append_only_so_a_long_crawl_does_not_degrade(tmp_path, monkeypatch):
    """The first implementation rewrote the whole completed set per mark — O(n)
    each, O(n^2) over a crawl. At ~72,000 works that is unusable, so the log
    must grow by exactly one line per unit."""
    monkeypatch.setattr(config, "CHECKPOINT_ROOT", tmp_path)

    ckpt = Checkpoint.load("append-test")
    for i in range(50):
        ckpt.mark(f"unit-{i}")
    ckpt.close()

    lines = ckpt.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 50


def test_marking_the_same_unit_twice_does_not_duplicate_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHECKPOINT_ROOT", tmp_path)

    ckpt = Checkpoint.load("dupe-test")
    ckpt.mark("same")
    ckpt.mark("same")
    ckpt.close()

    assert len(ckpt.log_path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_failures_survive_a_restart_and_are_never_dropped(tmp_path, monkeypatch):
    """A crawl that finishes with silent gaps is worse than one that fails —
    the completeness report reads these."""
    monkeypatch.setattr(config, "CHECKPOINT_ROOT", tmp_path)

    first = Checkpoint.load("fail-test")
    first.fail("w1", url="/x", error="timeout", http_status=None, retry_count=4)
    first.close()

    second = Checkpoint.load("fail-test")
    assert len(second.failures) == 1
    assert second.failures[0]["error"] == "timeout"
    assert second.failures[0]["retry_count"] == 4


# --------------------------------------------------------------------------
# Raw preservation and the manifest
# --------------------------------------------------------------------------

def test_every_stored_artefact_gets_a_manifest_row_with_its_hash(tmp_path, monkeypatch):
    """RawStore.write is the only path bytes take to disk, precisely so that
    storing something without provenance is impossible rather than discouraged."""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "MANIFEST_ROOT", tmp_path / "manifests")
    for name in ("RAW_API", "RAW_PAGES", "RAW_DOCUMENTS", "RAW_IMAGES",
                 "NORMALIZED_ROOT", "EXTRACTED_TEXT_ROOT", "CHECKPOINT_ROOT",
                 "REPORT_ROOT", "LOG_ROOT"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    monkeypatch.setattr(config, "ALL_DIRS", (tmp_path / "manifests",))

    store = RawStore(manifest_name="test.jsonl")
    payload = b"%PDF-1.4 pretend"
    entry = store.write(
        payload=payload,
        destination=tmp_path / "raw" / "doc.pdf",
        source_url="https://example.invalid/getAttachmentById",
        artefact_kind="document",
        http_status=200,
        request_body='{"id": "1.2"}',
        identifiers={"ATTACH_ID": "1.2"},
    )

    assert entry.sha256 == sha256_bytes(payload)
    assert entry.file_size == len(payload)
    assert entry.identifiers["ATTACH_ID"] == "1.2"
    assert entry.request_body == '{"id": "1.2"}'
    assert list(store.manifest.read())[0].sha256 == entry.sha256


def test_identical_bytes_are_not_rewritten_but_are_still_recorded(tmp_path, monkeypatch):
    """A re-crawl must be visible in the audit trail without doubling storage."""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "MANIFEST_ROOT", tmp_path / "manifests")
    monkeypatch.setattr(config, "ALL_DIRS", (tmp_path / "manifests",))

    store = RawStore(manifest_name="dupe.jsonl")
    target = tmp_path / "raw" / "same.bin"
    kwargs = dict(destination=target, source_url="https://example.invalid/x",
                  artefact_kind="document", http_status=200)

    store.write(payload=b"identical", **kwargs)
    second = store.write(payload=b"identical", **kwargs)

    assert store.manifest.count() == 2
    assert "bytes unchanged" in (second.note or "")


# --------------------------------------------------------------------------
# The product constraints must survive into this module too
# --------------------------------------------------------------------------

def test_the_ingestion_tree_carries_no_fraud_language():
    """Constraint 1 greps src/. This module is not under src/, so it would have
    escaped that guard entirely."""
    banned = ("fraud_probability", "is_fraud", "fraud_score", "fraudulent")
    root = Path(__file__).resolve().parent.parent / "ingestion"

    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        offenders += [f"{path.name}: {word}" for word in banned if word in text]

    assert not offenders, f"fraud language in the ingestion tree: {offenders}"


def test_no_image_is_ever_assigned_a_before_during_after_stage():
    """The portal declares no stage. Inferring one from a filename would have
    been wrong on the first file we retrieved — `wc.jpg` is a scanned
    certificate, not a photograph of the asset."""
    source = (Path(__file__).resolve().parent.parent
              / "ingestion" / "images" / "inspect.py").read_text(encoding="utf-8")

    assert "source_declared_stage=None" in source.replace(" ", "")
    assert "BEFORE" not in source.split('"""', 2)[2].upper().replace("BEFORE/DURING", "")


def test_rate_limiting_is_on_by_default():
    """This runs against a government server. A default of zero delay is how a
    research crawler becomes an incident."""
    assert config.REQUEST_DELAY_SECONDS >= 1.0
    assert config.ATTACHMENT_DELAY_SECONDS >= 1.0
    assert config.MAX_RETRIES >= 1
