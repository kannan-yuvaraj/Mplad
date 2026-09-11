"""The real engines, end to end: Surya on a photographed board, Docling on a work order.

The stand-in tests in test_ocr_engines.py pin the behaviour around the engines. These run
the engines themselves, so they are slow and need the models on disk:

* **Docling** runs whenever its layout models are in the Hugging Face cache (they arrive the
  first time a document is read).
* **Surya** starts a model server on the GPU and takes a minute, so it runs only when asked:
  ``MPLADS_TEST_SURYA=1 .venv/Scripts/python.exe -m pytest tests/test_ocr_real.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from mplads import ocr

REF, AMOUNT = "MP3018356-W86316", 65_000_000

ORDER = [
    "OFFICE OF THE DISTRICT PLANNING OFFICER, SARAN",
    "Sanction Order No. DPO/MPLADS/2024/118",
    f"Work No. {REF}",
    "Name of work: Construction of Outdoor Gym in 70 locations",
    "Sanctioned Amount: Rs 6,50,00,000",
    "Work No. MP3018356-W86317 (street lights), Sanctioned Amount: Rs 12,00,000",
]


def _font(size):
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _docling_models_cached() -> bool:
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return (cache / "models--docling-project--docling-layout-heron").exists()


@pytest.mark.skipif(not ocr.documents_available() or not _docling_models_cached(),
                    reason="Docling or its layout models are not on this machine")
@pytest.mark.parametrize("kind", ["digital_pdf", "scanned_png"])
def test_docling_reads_a_work_order(tmp_path, kind):
    if kind == "digital_pdf":
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in ORDER:
            pdf.cell(0, 9, line, new_x="LMARGIN", new_y="NEXT")
        path = tmp_path / "order.pdf"
        pdf.output(str(path))
    else:
        page = Image.new("RGB", (1500, 900), "white")
        draw = ImageDraw.Draw(page)
        for i, line in enumerate(ORDER):
            draw.text((50, 60 + i * 120), line, font=_font(30), fill="black")
        path = tmp_path / "order.png"
        page.rotate(0.8, fillcolor="white").filter(ImageFilter.GaussianBlur(0.6)).save(path)

    result = ocr.read_document(path)
    assert result["engine"] == "docling", result.get("error")
    assert result["work_refs"] == [REF, "MP3018356-W86317"]
    assert AMOUNT in result["amounts"] and 1_200_000 in result["amounts"]
    assert "Sanction Order" in result["markdown"]


@pytest.mark.skipif(os.environ.get("MPLADS_TEST_SURYA") != "1",
                    reason="set MPLADS_TEST_SURYA=1 to start Surya's model server")
def test_surya_reads_a_photographed_board_and_the_second_reader_checks_it(tmp_path):
    surya = ocr.ENGINES["surya"]
    assert surya.available(), f"Surya is not set up: {surya.missing()}"

    board = Image.new("RGB", (1100, 600), "#f2f0e8")
    draw = ImageDraw.Draw(board)
    draw.rectangle([0, 0, 1100, 90], fill="#1d4a2f")
    draw.text((40, 28), "MEMBER OF PARLIAMENT LOCAL AREA DEVELOPMENT SCHEME",
              font=_font(26), fill="white")
    for i, (label, value) in enumerate([("Work No.", REF),
                                        ("Sanctioned Amount", "\u20b9 6,50,00,000"),
                                        ("Implementing Agency", "District Planning Office, Saran")]):
        draw.text((50, 150 + i * 110), label + ":", font=_font(26), fill="#5c5346")
        draw.text((380, 150 + i * 110), value, font=_font(30), fill="#171310")
    path = tmp_path / "board.jpg"
    board.rotate(3, expand=True, fillcolor="#777").save(path, quality=80)

    try:
        result = ocr.read(path)
    finally:
        ocr.shutdown()
    assert result["engine"] == "surya", result
    assert result["fields"]["work_ref"]["value"] == REF
    assert result["fields"]["amount"]["value"] == AMOUNT
    assert result["cross_check"]["engine"] == "rapidocr"
    assert result["cross_check"]["agrees"] is True
