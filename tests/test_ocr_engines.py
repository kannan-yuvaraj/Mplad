"""The OCR engines: Surya for photographs, a second reader to check it, Docling for documents.

These run with stand-in engines, so they take milliseconds and need none of the models.
What they pin is the behaviour around the engines — the parts that decide whether an
officer is told the truth about what was read:

* a half-downloaded model is "not available", never a crash forty seconds into startup;
* a reader that fails hands the photograph to the next one instead of failing the upload;
* two readers that disagree force the officer to confirm, and the other reading is offered;
* a document's every work reference is found, and each is checked against the records.
"""

from __future__ import annotations

import json

import pytest

from mplads import config, field, ocr


class FakeEngine:
    """Returns fixed lines, or raises, and counts how often it was asked."""

    def __init__(self, name, lines=None, fail=False, label=None):
        self.name = name
        self.label = label or name.title()
        self._lines = lines or []
        self._fail = fail
        self.calls = 0

    def available(self):
        return True

    def lines(self, image):
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"{self.name} is down")
        return [{"text": t, "confidence": c} for t, c in self._lines]

    def status(self):
        return {"engine": self.name, "available": True}

    def stop(self):
        return None


@pytest.fixture
def board(tmp_path):
    from PIL import Image

    path = tmp_path / "board.png"
    Image.new("RGB", (400, 200), "white").save(path)
    return path


@pytest.fixture
def engines(monkeypatch):
    """Install stand-in engines in the configured order and hand back a setter."""
    def install(*fakes):
        monkeypatch.setattr(ocr, "ENGINES", {f.name: f for f in fakes})
        monkeypatch.setattr(config, "OCR_IMAGE_ENGINES", tuple(f.name for f in fakes))
    return install


# ------------------------------------------------------------------- Surya's HTML output


def test_surya_html_is_flattened_into_lines():
    html = "<p>MEMBER OF PARLIAMENT</p><p>Sanctioned Amount: Rs 6,50,00,000<br/>Date: 2024</p>"
    assert ocr._html_lines(html) == [
        "MEMBER OF PARLIAMENT", "Sanctioned Amount: Rs 6,50,00,000", "Date: 2024",
    ]


def test_a_two_column_board_keeps_each_label_with_its_value():
    """Boards are laid out as label | value. Split per cell, the reference loses its label
    and the amount loses its "Rs" — so cells on one row stay on one line."""
    html = ("<table><tr><td>Work No.</td><td>MP3018356-W86316</td></tr>"
            "<tr><td>Sanctioned Amount</td><td>Rs 6,50,00,000</td></tr></table>")
    lines = ocr._html_lines(html)
    assert lines == ["Work No. MP3018356-W86316", "Sanctioned Amount Rs 6,50,00,000"]
    fields = ocr._extract_fields([{"text": t, "confidence": None} for t in lines])
    assert fields["work_ref"]["value"] == "MP3018356-W86316"
    assert fields["amount"]["value"] == 65_000_000


@pytest.mark.parametrize("text, expected", [
    ("Sanctioned Amount: ? 499,950", 499_950),     # ₹ read as "?"
    ("Sanctioned Amount: 499,950", 499_950),       # ₹ dropped entirely
    ("Sanctioned Amount:  12,00,000", 1_200_000),
    ("Estimated Cost: 12.5 lakh", 1_250_000),
    ("Amount 6.5 Cr", 65_000_000),
])
def test_the_amount_is_found_by_its_label_when_the_rupee_sign_is_lost(text, expected):
    """General OCR models drop "₹" or read it as "?". Measured: RapidOCR lost it on every
    font tried, which left the amount unread on half the benchmark boards."""
    fields = ocr._extract_fields([{"text": text, "confidence": 0.9}])
    assert fields["amount"]["value"] == expected


def test_a_stray_small_number_after_amount_is_not_taken_for_a_sanction():
    fields = ocr._extract_fields([{"text": "Recommended On: 2024-01-21 Amount: 2", "confidence": 1}])
    assert "amount" not in fields


def test_html_entities_are_decoded():
    assert ocr._html_lines("<p>Road &amp; drain, Rs&nbsp;5 lakh</p>") == ["Road & drain, Rs 5 lakh"]


# ------------------------------------------------------------- is Surya really available


def _manifest(tmp_path, sizes):
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"files": {name: {"size": size, "sha256": "x"} for name, size in sizes.items()}}))


def test_a_half_downloaded_model_is_not_available(monkeypatch, tmp_path):
    """The file exists and has a valid header; it is still not the model."""
    monkeypatch.setattr(config, "SURYA_GGUF_DIR", tmp_path)
    monkeypatch.setattr(config, "SURYA_GGUF_MODEL", tmp_path / "surya-2.gguf")
    monkeypatch.setattr(config, "SURYA_GGUF_MMPROJ", tmp_path / "surya-2-mmproj.gguf")
    (tmp_path / "surya-2.gguf").write_bytes(b"GGUF" + b"\0" * 96)
    (tmp_path / "surya-2-mmproj.gguf").write_bytes(b"GGUF" + b"\0" * 96)

    assert ocr._surya_model_gaps(), "no manifest yet, so not verified"

    _manifest(tmp_path, {"surya-2.gguf": 10_000, "surya-2-mmproj.gguf": 100})
    gaps = ocr._surya_model_gaps()
    assert len(gaps) == 1 and "surya-2.gguf" in gaps[0], "the short file must be named"

    _manifest(tmp_path, {"surya-2.gguf": 100, "surya-2-mmproj.gguf": 100})
    assert ocr._surya_model_gaps() == []


def test_surya_without_a_verified_model_reports_what_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SURYA_GGUF_DIR", tmp_path)
    monkeypatch.setattr(config, "SURYA_GGUF_MODEL", tmp_path / "surya-2.gguf")
    monkeypatch.setattr(config, "SURYA_GGUF_MMPROJ", tmp_path / "surya-2-mmproj.gguf")
    surya = ocr._Surya()
    assert surya.available() is False
    assert any("fetch_ocr_models" in gap for gap in surya.missing())
    assert surya.start() is False, "must refuse to start, not try and crash"


def test_a_surya_that_failed_to_start_stays_off(monkeypatch):
    """One dead start is remembered, so later photographs do not each wait on it."""
    surya = ocr._Surya()
    monkeypatch.setattr(surya, "missing", lambda: [])
    surya._failed = "RuntimeError: llama-server exited"
    assert surya.available() is False
    assert surya.status()["failed"].startswith("RuntimeError")


# ------------------------------------------------------------------ reading a photograph


def test_the_first_reader_reads_and_the_second_checks(engines, board):
    primary = FakeEngine("surya", [("Work No. MP3018356-W86316", None)], label="Surya OCR 2")
    second = FakeEngine("rapidocr", [("Work No. MP3018356-W86316", 0.97)], label="RapidOCR")
    engines(primary, second)

    result = ocr.read(board)
    assert result["engine"] == "surya"
    assert result["fields"]["work_ref"]["value"] == "MP3018356-W86316"
    assert result["fields"]["work_ref"]["confidence"] is None, "Surya gives no figure"
    check = result["cross_check"]
    assert check["engine"] == "rapidocr" and check["agrees"] is True
    assert check["confidence"] == 0.97
    assert primary.calls == 1 and second.calls == 1


def test_a_failed_reader_hands_the_photograph_to_the_next(engines, board):
    engines(FakeEngine("surya", fail=True),
            FakeEngine("rapidocr", [("MP3018356-W86316", 0.9)]))
    result = ocr.read(board)
    assert result["engine"] == "rapidocr"
    assert result["fell_back_from"] == "surya"
    assert result["fields"]["work_ref"]["value"] == "MP3018356-W86316"
    assert "cross_check" not in result, "nothing left to check against"


def test_every_reader_failing_is_an_error_not_an_empty_success(engines, board):
    engines(FakeEngine("surya", fail=True), FakeEngine("rapidocr", fail=True))
    result = ocr.read(board)
    assert result["fields"] == {}
    assert "error" in result


def test_the_cross_check_can_be_switched_off(engines, board):
    second = FakeEngine("rapidocr", [("MP3018356-W86316", 0.9)])
    engines(FakeEngine("surya", [("MP3018356-W86316", None)]), second)
    result = ocr.read(board, cross_check=False)
    assert "cross_check" not in result and second.calls == 0


# ------------------------------------------------------------------ two readers disagree


def test_readers_that_disagree_force_a_confirmation(engines, board):
    """Both references are real works. Neither reader's confidence can settle it."""
    engines(FakeEngine("surya", [("MP3017167-W136962", None)], label="Surya OCR 2"),
            FakeEngine("rapidocr", [("MP3017167-W136963", 0.996)], label="RapidOCR"))
    extracted = ocr.read(board)
    assert extracted["cross_check"]["agrees"] is False

    known = {"MP3017167-W136962", "MP3017167-W136963"}
    verdict = ocr.match_to_work(extracted, known)
    assert verdict["matched"] is True
    assert verdict["needs_confirmation"] is True
    assert verdict["readers_agree"] is False
    assert "MP3017167-W136963" in verdict["alternatives"]
    assert "disagree" in verdict["reason"]


def test_readers_that_agree_on_an_unambiguous_work_need_no_confirmation(engines, board):
    engines(FakeEngine("surya", [("MP3018356-W86316", None)]),
            FakeEngine("rapidocr", [("MP3018356-W86316", 0.99)]))
    verdict = ocr.match_to_work(ocr.read(board), {"MP3018356-W86316"})
    assert verdict["needs_confirmation"] is False
    assert verdict["readers_agree"] is True


def test_one_reader_finding_nothing_is_not_counted_as_agreement(engines, board):
    engines(FakeEngine("surya", [("MP3018356-W86316", None)]),
            FakeEngine("rapidocr", [("an unreadable smudge", 0.4)]))
    assert ocr.read(board)["cross_check"]["agrees"] is None


# ------------------------------------------------------------------------------ documents


class FakeDocling:
    name, label = "docling", "Docling"

    def __init__(self, text):
        self.text = text

    def available(self):
        return True

    def convert(self, path):
        lines = [l for l in self.text.splitlines() if l.strip()]
        return {"markdown": self.text, "lines": [{"text": l, "confidence": None} for l in lines],
                "pages": 1, "status": "SUCCESS"}


def test_a_document_returns_every_work_it_mentions(monkeypatch, tmp_path):
    order = """## Sanction Order No. DPO/MPLADS/2024/118
| Work No. | Work | Amount |
| MP3018356-W86316 | Outdoor gym | Rs 6,50,00,000 |
| MP3018356-W86317 | Street lights | Rs 12,00,000 |
Copy to: MP3018356-W86316 file."""
    monkeypatch.setattr(ocr, "DOCUMENT_ENGINE", FakeDocling(order))
    result = ocr.read_document(tmp_path / "order.pdf")
    assert result["engine"] == "docling"
    assert result["work_refs"] == ["MP3018356-W86316", "MP3018356-W86317"], "each once, in order"
    assert result["fields"]["work_ref"]["value"] == "MP3018356-W86316"
    assert 65_000_000 in result["amounts"] and 1_200_000 in result["amounts"]
    assert "| Work No. |" in result["markdown"], "tables survive as Markdown"


def test_a_document_reader_that_is_missing_degrades_to_a_note(monkeypatch, tmp_path):
    class Missing(FakeDocling):
        def available(self):
            return False
    monkeypatch.setattr(ocr, "DOCUMENT_ENGINE", Missing(""))
    result = ocr.read_document(tmp_path / "order.pdf")
    assert result["available"] is False and result["work_refs"] == []


def test_a_document_that_cannot_be_read_says_so(monkeypatch, tmp_path):
    class Broken(FakeDocling):
        def convert(self, path):
            raise ValueError("encrypted PDF")
    monkeypatch.setattr(ocr, "DOCUMENT_ENGINE", Broken(""))
    result = ocr.read_document(tmp_path / "order.pdf")
    assert "encrypted PDF" in result["error"]


def test_uploaded_documents_are_stored_by_content_not_by_the_name_given(monkeypatch, tmp_path):
    monkeypatch.setattr(field, "DOCUMENTS", tmp_path / "docs")
    pdf = b"%PDF-1.4 a sanction order"
    name = field.save_document(pdf, "../../etc/passwd.pdf")
    assert (tmp_path / "docs" / name).read_bytes() == pdf
    assert "/" not in name and ".." not in name
    assert field.save_document(pdf, "again.pdf") == name, "same bytes, stored once"


def test_a_file_named_pdf_that_is_not_a_pdf_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(field, "DOCUMENTS", tmp_path / "docs")
    with pytest.raises(ValueError, match="not a PDF"):
        field.save_document(b"MZ\x90\x00 an executable", "order.pdf")
    with pytest.raises(ValueError, match="unsupported"):
        field.save_document(b"#!/bin/sh", "order.sh")


# ------------------------------------------------------------------ the verification record


def test_the_record_keeps_which_reader_read_the_board_and_the_document(monkeypatch, tmp_path):
    monkeypatch.setattr(field, "DB", tmp_path / "v.sqlite")
    monkeypatch.setattr(field, "PHOTOS", tmp_path / "photos")
    field.record("MP3018356-W86316", "VERIFIED_IN_PROGRESS", actor="t", role="auditor",
                 board_ref="MP3018356-W86316", ocr_engine="surya", readers_agree=True,
                 document="abc123.pdf")
    row = field.for_work("MP3018356-W86316")[0]
    assert row["ocr_engine"] == "surya"
    assert row["readers_agree"] == 1
    assert row["document"] == "abc123.pdf"


# ----------------------------------------------------------------------------------- API


def test_the_api_reports_which_readers_this_machine_has():
    from fastapi.testclient import TestClient
    from mplads.api.app import app

    body = TestClient(app).get("/api/ocr/status").json()
    assert {"photographs", "documents"} <= set(body)
    assert body["photographs"]["order"] == list(config.OCR_IMAGE_ENGINES)
    assert body["documents"]["engine"] == "docling"


def test_the_document_endpoint_checks_every_reference_against_the_records(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from mplads.api.app import app, store

    if not (config.ARTIFACTS / "case_files.json").exists():
        pytest.skip("run the pipeline first")
    real = store().worklist[0]["work_ref"]
    monkeypatch.setattr(field, "DOCUMENTS", tmp_path / "docs")
    monkeypatch.setattr(ocr, "DOCUMENT_ENGINE",
                        FakeDocling(f"Work No. {real}\nAlso MP9999999-W99999"))

    response = TestClient(app).post(
        "/api/ocr/document",
        files={"file": ("order.pdf", b"%PDF-1.4 order", "application/pdf")},
        data={"work_ref": real},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mentions_this_work"] is True
    found = {r["work_ref"]: r["known"] for r in body["refs_found"]}
    assert found == {real: True, "MP9999999-W99999": False}
    assert body["document"].endswith(".pdf")


def test_the_document_endpoint_refuses_a_disguised_file(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from mplads.api.app import app

    monkeypatch.setattr(field, "DOCUMENTS", tmp_path / "docs")
    response = TestClient(app).post(
        "/api/ocr/document", files={"file": ("order.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 400
