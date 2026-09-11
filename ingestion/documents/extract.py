"""Phase 6 — text extraction from downloaded documents.

The original file is never modified. Extracted text is written alongside it in
`extracted_text/`, keyed by the same attachment id, so the derived text and the
government original stay linked but distinct.

`pypdf` is a soft dependency. It is not in `pyproject.toml` because adding a
dependency to this project requires asking first, so extraction degrades to
"recorded as unavailable" rather than failing the pipeline. Install it with::

    python -m uv pip install --python .venv/Scripts/python.exe pypdf

OCR is deliberately NOT wired to a fallback here. The sample completion
certificate we retrieved is a photographed, handwritten-annotated Marathi
document; running OCR over it and storing the output as if it were the
document's contents would manufacture text that nobody can trust. When OCR is
added it must record its confidence and be marked as machine-read.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ingestion import config
from ingestion.storage.manifest import ManifestWriter, RawStore

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Extraction:
    attach_id: str
    source_path: str
    method: str          # 'pdf_text' | 'plain_text' | 'unavailable'
    characters: int
    output_path: str | None
    note: str | None = None


def extract_pdf_text(path: Path) -> tuple[str, str]:
    """Return (text, method). Raises nothing — reports unavailability instead."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "unavailable"
    try:
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            # Page number is kept inline so a provenance chain can point at
            # "completion_certificate.pdf, page 2" rather than at the file.
            pages.append(f"\n\n===== PAGE {index} =====\n{page.extract_text() or ''}")
        return "".join(pages), "pdf_text"
    except Exception as exc:  # pypdf raises a wide variety on malformed files
        log.warning("pdf extraction failed for %s: %s", path, exc)
        return "", "unavailable"


def run_extraction() -> dict[str, Any]:
    """Extract text from every stored document. Idempotent."""
    config.ensure_dirs()
    store = RawStore()
    manifest = ManifestWriter(config.MANIFEST_ROOT / "manifest.jsonl")

    results: list[Extraction] = []
    for entry in manifest.read():
        if entry.artefact_kind != "document":
            continue
        source = config.DATA_ROOT / entry.stored_path
        if not source.exists():
            continue

        attach_id = str(entry.identifiers.get("ATTACH_ID", source.stem))
        work_id = str(entry.identifiers.get("WORK_RECOMMENDATION_DTL_ID", "unknown"))
        suffix = source.suffix.lower()

        if suffix == ".pdf":
            text, method = extract_pdf_text(source)
        elif suffix == ".txt":
            text, method = source.read_text(encoding="utf-8", errors="replace"), "plain_text"
        else:
            text, method = "", "unavailable"

        output: Path | None = None
        if text.strip():
            output = config.EXTRACTED_TEXT_ROOT / work_id / f"{attach_id}.txt"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")

        note = None
        if method == "unavailable":
            note = ("pypdf not installed" if suffix == ".pdf" else f"no extractor for {suffix}")
        elif not text.strip():
            note = "extractor produced no text — likely a scanned image; OCR not run"

        results.append(Extraction(
            attach_id=attach_id, source_path=entry.stored_path, method=method,
            characters=len(text), output_path=str(output) if output else None, note=note,
        ))

    summary = {
        "documents_seen": len(results),
        "text_extracted": sum(1 for r in results if r.characters > 0),
        "no_text": sum(1 for r in results if r.characters == 0),
        "by_method": {
            m: sum(1 for r in results if r.method == m)
            for m in {r.method for r in results}
        },
        "detail": [r.__dict__ if hasattr(r, "__dict__") else
                   {f: getattr(r, f) for f in r.__slots__} for r in results],
    }
    store.write_json(obj=summary, destination=config.REPORT_ROOT / "extraction_summary.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return summary
