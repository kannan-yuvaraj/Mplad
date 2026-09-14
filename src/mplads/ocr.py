"""Read a site photograph or a work document and pull the fields that identify a work.

MPLADS works carry a display board at the site: work reference, sanctioned amount,
implementing district. An officer photographs that board; this reads it and matches the
record, so nobody re-types a reference number standing in a field. The same officer often
also holds paper — a sanction order, a work order, a completion certificate — and that is
read too.

Two jobs, two engines:

* **Photographs of site boards → Surya** (``surya-ocr-2``, a vision-language OCR model run
  locally by llama.cpp). A second, independent reader (RapidOCR) reads the same photograph,
  and the two are compared. Two readers agreeing on a reference is evidence; one reader at
  "99%" is not — a weathered board reads one digit wrong at high confidence and lands on a
  different real work. Where Surya is not installed or will not start, RapidOCR reads alone.
* **Documents → Docling**, which keeps the page's structure (headings, tables, reading
  order) and runs OCR only where a page has no text layer. Every work reference in the
  document is returned, not just the first — an order often sanctions several works.

**What this is not.** It does not verify that the work exists, or that it matches its
description, or that the money was spent. It reads text off an image the officer supplies.
Every extracted field is returned with where it came from and is shown for confirmation —
the officer accepts or corrects it before anything is recorded.

If no engine is available the module degrades to manual entry rather than failing: the
officer types the reference.
"""

from __future__ import annotations

import atexit
import html as _html
import importlib.util
import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from mplads import config

LOGGER = logging.getLogger(__name__)

#: Letters an OCR engine returns where a digit was printed. Weathered signage and low
#: light make these the standard substitutions; the reference is all digits, so correcting
#: them is safe in a way it would not be inside free text.
CONFUSIONS = str.maketrans({
    "O": "0", "o": "0",
    "I": "1", "i": "1", "l": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "B": "8",
})

#: The character class the reference may be *read* as — derived from the correction table
#: rather than written out, so the two can never drift apart. That drift is exactly the bug
#: this replaced: the pattern admitted only O, so "W863I6" matched as "W863" and the last
#: two characters were silently dropped from the reference.
_DIGITISH = "[" + re.escape("".join(sorted(chr(o) for o in CONFUSIONS))) + r"\d]"

#: Our canonical reference, e.g. MP3018356-W86316. OCR also drops spaces and renders the
#: hyphen as any dash it likes, so the pattern tolerates that and normalises afterwards.
WORK_REF = re.compile(
    rf"MP\s*({_DIGITISH}{{5,10}})\s*[-–—_]\s*W\s*({_DIGITISH}{{2,10}})", re.I
)

#: "Rs 6,50,00,000" / "₹6.5 Cr" / "Amount: 650000"
AMOUNT = re.compile(
    r"(?:rs|inr|₹)\s*\.?\s*([\d,]+(?:\.\d+)?)\s*(cr|crore|lakh|lac|l)?", re.I
)

#: The amount by its label, for when the currency sign is lost. Boards print "₹", and a
#: general-purpose OCR model often drops it or reads it as "?" — measured on rendered boards:
#: RapidOCR lost the sign on every font tried, which left the amount unread on half the
#: benchmark. The label is printed in plain letters and survives. At least three digits, so
#: a stray "Amount: 2" in a heading is not taken for a sanction.
LABELLED_AMOUNT = re.compile(
    r"(?:sanction(?:ed)?|approved|estimated|recommended)?\s*(?:amount|cost)\b[^\d\n]{0,12}?"
    r"(?:rs\.?|inr|₹|\?)?\s*"
    r"(\d[\d,]{2,}(?:\.\d+)?|\d+(?:\.\d+)?(?=\s*(?:cr|crore|lakh|lac)\b))"
    r"\s*(cr|crore|lakh|lac|l)?\b",
    re.I,
)

#: Photographs bigger than this are downscaled before reading. Accuracy on a board is
#: unchanged and it is much faster.
MAX_SIDE = 2000


# =============================================================================== engines
#
# Each engine turns an image into lines: [{"text": str, "confidence": float | None}].
# `confidence` is the engine's confidence in the *characters* of that line, where the
# engine reports one. Surya does not; RapidOCR does. It is never confidence in the answer.


class _RapidOCR:
    """PP-OCRv4 through ONNX Runtime. Small, CPU-only, no download — the model ships
    inside the wheel. The fallback reader and the second opinion."""

    name = "rapidocr"
    label = "RapidOCR (PP-OCRv4)"

    def __init__(self) -> None:
        self._engine = None
        self._tried = False
        self._lock = threading.Lock()

    def available(self) -> bool:
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None and (
            self._engine is not None or not self._tried or self._load() is not None
        )

    def _load(self):
        with self._lock:
            if self._tried:
                return self._engine
            self._tried = True
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("could not start RapidOCR: %s", exc)
                self._engine = None
            return self._engine

    def lines(self, image) -> list[dict]:
        import numpy as np

        engine = self._load()
        if engine is None:
            raise RuntimeError("RapidOCR is not available")
        result, _ = engine(np.array(image))
        return [
            {"text": text, "confidence": round(float(conf), 3)}
            for _, text, conf in (result or [])
        ]

    def status(self) -> dict:
        return {"engine": self.name, "label": self.label, "available": self.available(),
                "loaded": self._engine is not None, "role": "second reader and fallback"}

    def stop(self) -> None:
        return None


def _winget_llama_server() -> Path | None:
    """Where `winget install ggml.llamacpp` puts the binary, on the machine that has it."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not packages.exists():
        return None
    for candidate in sorted(packages.glob("ggml.llamacpp*/llama-server.exe")):
        return candidate
    return None


def llama_server_binary() -> str | None:
    """The llama-server executable Surya runs on, or None when there is none."""
    if config.LLAMA_SERVER and Path(config.LLAMA_SERVER).is_file():
        return config.LLAMA_SERVER
    found = shutil.which(config.LLAMA_SERVER or "llama-server")
    if found:
        return found
    winget = _winget_llama_server()
    return str(winget) if winget else None


def _html_lines(fragment: str) -> list[str]:
    """Surya returns each layout block as a little HTML fragment. Flatten it to lines.

    Table cells on one row are joined with a space rather than split, because a board is
    often laid out as a two-column table — "Work No." | "MP3018356-W86316" — and the label
    and the value belong on one line for the field patterns to find them together.
    """
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|caption|thead|tbody)>", "\n", fragment)
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.split("\n") if line.strip()]


def _surya_model_gaps() -> list[str]:
    """Why Surya's model files cannot be used yet — empty when they can.

    Present is not enough. A download that stopped halfway leaves a file with a valid
    header that makes llama-server fail forty seconds into startup, so the files must match
    the size recorded in the manifest `scripts/fetch_ocr_models.py` writes after checking
    them against Hugging Face. (Size, not the hash, is re-checked here: hashing 1.5 GB on
    every availability check would cost seconds; the fetch script already hashed them.)
    """
    manifest = config.SURYA_GGUF_DIR / "manifest.json"
    if not manifest.is_file():
        return [f"a verified Surya model in {config.SURYA_GGUF_DIR} "
                "(run scripts/fetch_ocr_models.py)"]
    try:
        files = json.loads(manifest.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        return ["a readable Surya model manifest (re-run scripts/fetch_ocr_models.py)"]
    gaps = []
    for path in (config.SURYA_GGUF_MODEL, config.SURYA_GGUF_MMPROJ):
        want = (files.get(path.name) or {}).get("size")
        if not path.is_file() or want is None or path.stat().st_size != want:
            gaps.append(f"a complete {path.name} (re-run scripts/fetch_ocr_models.py)")
    return gaps


class _Surya:
    """Surya OCR 2 — a vision-language model that returns a page's layout and its text in
    one pass. Run locally by llama.cpp's `llama-server`, which Surya starts and owns.

    The server takes tens of seconds to load the model, so it is started once per process
    (the API warms it in the background at startup) and kept. If it will not start, the
    failure is remembered and Surya reports itself unavailable, so every later photograph
    goes straight to the fallback reader instead of waiting on a dead server again.
    """

    name = "surya"
    label = "Surya OCR 2"

    def __init__(self) -> None:
        self._manager = None
        self._predictor = None
        self._failed: str | None = None
        self._start_lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._started_at: float | None = None
        self._startup_seconds: float | None = None
        self._last_read_seconds: float | None = None

    def missing(self) -> list[str]:
        """What this machine lacks to run Surya — empty when it can."""
        gaps = []
        if importlib.util.find_spec("surya") is None:
            gaps.append("the surya-ocr Python package")
        if llama_server_binary() is None:
            gaps.append("the llama-server binary (winget install ggml.llamacpp)")
        gaps.extend(_surya_model_gaps())
        return gaps

    def available(self) -> bool:
        return self._failed is None and not self.missing()

    def _configure_environment(self) -> None:
        """Surya reads its settings from the environment when it is first imported."""
        os.environ.setdefault("SURYA_INFERENCE_BACKEND", "llamacpp")
        os.environ["LLAMA_CPP_BINARY"] = llama_server_binary() or "llama-server"
        os.environ["SURYA_GGUF_LOCAL_MODEL_PATH"] = str(config.SURYA_GGUF_MODEL)
        os.environ["SURYA_GGUF_LOCAL_MMPROJ_PATH"] = str(config.SURYA_GGUF_MMPROJ)
        os.environ.setdefault("SURYA_INFERENCE_STARTUP_TIMEOUT", str(config.SURYA_STARTUP_TIMEOUT))
        if config.LLAMA_DEVICE:
            os.environ.setdefault("LLAMA_CPP_EXTRA_ARGS", f"--device {config.LLAMA_DEVICE}")
        # Hugging Face's Xet transfer client stalls at 0 bytes on some networks; plain HTTP
        # works everywhere. Only matters if Surya falls back to its layout model.
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    def start(self) -> bool:
        """Start the server if it is not running. True when Surya is ready to read."""
        if self._predictor is not None:
            return True
        with self._start_lock:
            if self._predictor is not None:
                return True
            if self._failed is not None or self.missing():
                return False
            began = time.time()
            self._started_at = began
            try:
                self._configure_environment()
                from surya.inference import SuryaInferenceManager
                from surya.recognition import RecognitionPredictor

                manager = SuryaInferenceManager(method="llamacpp")
                manager.start()
                predictor = RecognitionPredictor(manager)
                predictor.disable_tqdm = True
            except Exception as exc:
                self._failed = f"{type(exc).__name__}: {exc}"[:400]
                LOGGER.warning("Surya did not start (%s) — photographs fall back to RapidOCR",
                               self._failed)
                return False
            self._manager, self._predictor = manager, predictor
            self._startup_seconds = round(time.time() - began, 1)
            LOGGER.info("Surya ready in %ss", self._startup_seconds)
            return True

    def lines(self, image) -> list[dict]:
        if not self.start():
            raise RuntimeError(self._failed or "Surya is not available")
        with self._read_lock:
            began = time.time()
            page = self._predictor([image], full_page=True)[0]
            # A vision-language model writes its answer a token at a time: ~20 s a board on a
            # 4 GB laptop GPU. Kept so the screen can tell the officer how long to wait.
            self._last_read_seconds = round(time.time() - began, 1)
        out: list[dict] = []
        for block in sorted(page.blocks, key=lambda b: b.reading_order):
            if block.skipped or not block.html:
                continue
            for text in _html_lines(block.html):
                out.append({"text": text, "confidence": None, "block": block.label})
        return out

    def status(self) -> dict:
        return {
            "engine": self.name, "label": self.label, "available": self.available(),
            "loaded": self._predictor is not None,
            "starting": self._predictor is None and self._start_lock.locked(),
            "startup_seconds": self._startup_seconds,
            "last_read_seconds": self._last_read_seconds,
            "failed": self._failed, "missing": self.missing(),
            "device": config.LLAMA_DEVICE or "llama.cpp default",
            "role": "primary reader for site photographs",
        }

    def stop(self) -> None:
        if self._manager is not None:
            try:
                self._manager.stop()
            except Exception:  # pragma: no cover - shutting down anyway
                pass
        self._manager = self._predictor = None


class _Docling:
    """Docling — converts a PDF or a scanned page into a structured document (headings,
    paragraphs, tables, in reading order). A PDF that already has a text layer is read
    from it directly; OCR runs only on pages that are pictures of paper.

    Its OCR step uses the PP-OCRv6 models that ship inside the rapidocr wheel, so reading
    a scanned page needs no model download beyond Docling's own layout models."""

    name = "docling"
    label = "Docling"

    def __init__(self) -> None:
        self._converter = None
        self._failed: str | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        if not config.DOCUMENT_OCR:
            return False
        return self._failed is None and importlib.util.find_spec("docling") is not None

    def _ocr_options(self):
        from docling.datamodel.pipeline_options import RapidOcrOptions

        # The PP-OCRv6 models bundled inside the rapidocr wheel — no download, and a newer
        # recogniser than the v4 one the photograph fallback uses.
        return RapidOcrOptions(backend="onnxruntime")

    def converter(self):
        if self._converter is not None:
            return self._converter
        with self._lock:
            if self._converter is not None:
                return self._converter
            os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import (
                DocumentConverter, ImageFormatOption, PdfFormatOption,
            )

            options = PdfPipelineOptions()
            options.do_ocr = True
            options.do_table_structure = True
            options.ocr_options = self._ocr_options()
            self._converter = DocumentConverter(format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            })
            return self._converter

    def convert(self, path: Path) -> dict:
        try:
            result = self.converter().convert(str(path))
        except Exception as exc:
            LOGGER.warning("Docling could not read %s: %s", path.name, exc)
            raise
        document = result.document
        markdown = document.export_to_markdown()
        lines = [line.strip() for line in document.export_to_text().splitlines() if line.strip()]
        return {
            "markdown": markdown,
            "lines": [{"text": line, "confidence": None} for line in lines],
            "pages": len(getattr(document, "pages", {}) or {}),
            "status": str(getattr(result, "status", "")),
        }

    def status(self) -> dict:
        return {"engine": self.name, "label": self.label, "available": self.available(),
                "loaded": self._converter is not None, "failed": self._failed,
                "role": "documents: sanction orders, work orders, certificates"}

    def stop(self) -> None:
        return None


ENGINES: dict[str, object] = {"surya": _Surya(), "rapidocr": _RapidOCR()}
DOCUMENT_ENGINE = _Docling()


def _image_engines() -> list:
    """The configured photograph readers that can actually run here, in order."""
    return [ENGINES[name] for name in config.OCR_IMAGE_ENGINES
            if name in ENGINES and ENGINES[name].available()]


def _engine():
    """The primary photograph reader, or None when no engine is usable."""
    usable = _image_engines()
    return usable[0] if usable else None


def available() -> bool:
    return _engine() is not None


def documents_available() -> bool:
    return DOCUMENT_ENGINE.available()


def warm() -> None:
    """Start the slow engine ahead of the first photograph. Safe to call more than once."""
    primary = _engine()
    if primary is not None and hasattr(primary, "start"):
        primary.start()


def warm_in_background() -> threading.Thread:
    thread = threading.Thread(target=warm, name="ocr-warm", daemon=True)
    thread.start()
    return thread


def status() -> dict:
    """What can read what on this machine, for the API and the screen."""
    primary = _engine()
    return {
        "photographs": {
            "order": list(config.OCR_IMAGE_ENGINES),
            "primary": primary.name if primary else None,
            "engines": [engine.status() for engine in ENGINES.values()],
        },
        "documents": DOCUMENT_ENGINE.status(),
    }


@atexit.register
def shutdown() -> None:
    """Stop any server an engine started. llama-server must not outlive the API."""
    for engine in ENGINES.values():
        engine.stop()


# ================================================================================ fields


def _normalise_ref(prefix: str, serial: str) -> str:
    return f"MP{prefix.translate(CONFUSIONS)}-W{serial.translate(CONFUSIONS)}"


def _parse_amount(raw: str, unit: str | None) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith("cr"):
        return value * 1e7
    if unit in {"lakh", "lac", "l"}:
        return value * 1e5
    return value


def _line_confidence(fragment: str, lines: list[dict]) -> float | None:
    """How sure the engine was about the line this fragment came from.

    This is confidence in the *characters*, not in the answer — a weathered board returns
    a wrong digit at high confidence quite happily. It is shown so an officer knows how
    legible the board was, never as a reason to skip confirming the field. None when the
    engine does not report one (Surya).
    """
    needle = fragment.replace(" ", "")
    scores = [line["confidence"] for line in lines
              if line.get("confidence") is not None and needle in line["text"].replace(" ", "")]
    return max(scores) if scores else None


def _extract_fields(lines: list[dict]) -> dict[str, dict]:
    """The first work reference and the first amount, with the text each came from."""
    blob = " ".join(line["text"] for line in lines)
    fields: dict[str, dict] = {}

    match = WORK_REF.search(blob)
    if match:
        fields["work_ref"] = {
            "value": _normalise_ref(match.group(1), match.group(2)),
            "source_text": match.group(0),
            "confidence": _line_confidence(match.group(0), lines),
        }

    for pattern in (AMOUNT, LABELLED_AMOUNT):
        money = pattern.search(blob)
        parsed = _parse_amount(money.group(1), money.group(2)) if money else None
        if parsed:
            fields["amount"] = {
                "value": parsed,
                "source_text": money.group(0).strip(),
                "confidence": _line_confidence(money.group(0), lines),
            }
            break
    return fields


def _all_refs(lines: list[dict]) -> list[str]:
    """Every distinct work reference in the text, in the order they appear."""
    blob = " ".join(line["text"] for line in lines)
    seen: dict[str, None] = {}
    for match in WORK_REF.finditer(blob):
        seen.setdefault(_normalise_ref(match.group(1), match.group(2)), None)
    return list(seen)


def _all_amounts(lines: list[dict]) -> list[float]:
    blob = " ".join(line["text"] for line in lines)
    found: dict[float, None] = {}
    for pattern in (AMOUNT, LABELLED_AMOUNT):
        for m in pattern.finditer(blob):
            value = _parse_amount(m.group(1), m.group(2))
            if value:
                found.setdefault(value, None)
    return list(found)


def _load_image(image_path: Path):
    from PIL import Image, ImageOps

    image = Image.open(image_path)
    image = ImageOps.exif_transpose(image).convert("RGB")  # phone photos arrive rotated
    if max(image.size) > MAX_SIDE:
        scale = MAX_SIDE / max(image.size)
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    return image


# ================================================================================ reading


def read(image_path: Path, *, cross_check: bool = True) -> dict:
    """Extract text and identifying fields from a photograph of a site board.

    Returns the raw lines, whichever fields were recognised, which engine read them, and —
    when a second engine is available — what that engine read, so the officer can see
    whether two independent readers agree. Nothing here is trusted: the caller shows it to
    the officer for confirmation.
    """
    primary = _engine()
    if primary is None:
        return {
            "available": False,
            "lines": [],
            "fields": {},
            "note": "Photo reading is unavailable on this machine. Enter the work "
                    "reference manually.",
        }

    try:
        image = _load_image(image_path)
    except Exception as exc:
        return {"available": True, "lines": [], "fields": {}, "error": f"unreadable image: {exc}"}

    readers = [primary] + [e for e in _image_engines() if e is not primary]
    used, lines, fell_back_from, seconds = None, [], None, None
    failed: set[str] = set()
    for engine in readers:
        began = time.time()
        try:
            lines = engine.lines(image)
            used, seconds = engine, round(time.time() - began, 2)
            break
        except Exception as exc:
            LOGGER.warning("ocr: %s failed on %s (%s)", engine.name, Path(image_path).name, exc)
            failed.add(engine.name)
            fell_back_from = fell_back_from or engine.name
    if used is None:
        return {"available": True, "lines": [], "fields": {},
                "error": "no reader could process this image"}

    fields = _extract_fields(lines)
    result: dict = {
        "available": True,
        "kind": "photograph",
        "engine": used.name,
        "engine_label": used.label,
        "seconds": seconds,
        "lines": lines,
        "fields": fields,
        "note": "Extracted text only. It has not been verified against any record — "
                "confirm or correct each field before saving.",
    }
    if fell_back_from:
        result["fell_back_from"] = fell_back_from

    # A reader that has just failed on this photograph is not asked again as the checker.
    second = next((e for e in _image_engines()
                   if e is not used and e.name not in failed), None) if cross_check else None
    if second is not None:
        result["cross_check"] = _cross_check(second, image, fields)

    LOGGER.info("ocr: %s read %s lines, fields %s%s", used.name, len(lines), list(fields),
                f", second reader agrees={result['cross_check']['agrees']}"
                if "cross_check" in result else "")
    return result


def _cross_check(engine, image, fields: dict) -> dict:
    """Read the same photograph with a second, independent engine and compare."""
    began = time.time()
    try:
        lines = engine.lines(image)
    except Exception as exc:
        return {"engine": engine.name, "engine_label": engine.label, "error": str(exc)[:200],
                "work_ref": None, "agrees": None}
    theirs = _extract_fields(lines)
    mine_ref = (fields.get("work_ref") or {}).get("value")
    their_ref = (theirs.get("work_ref") or {}).get("value")
    return {
        "engine": engine.name,
        "engine_label": engine.label,
        "seconds": round(time.time() - began, 2),
        "work_ref": their_ref,
        "amount": (theirs.get("amount") or {}).get("value"),
        # Their confidence in the characters of the reference line, where they give one.
        "confidence": (theirs.get("work_ref") or {}).get("confidence"),
        # None when either reader found no reference at all: nothing to agree about.
        "agrees": (mine_ref == their_ref) if (mine_ref and their_ref) else None,
    }


def read_document(path: Path) -> dict:
    """Read a sanction order, work order or certificate (PDF or scan) with Docling.

    Returns the document as Markdown (so its tables survive), its plain lines, the first
    reference and amount in the same shape `read` uses, and every reference and amount
    found — an order routinely covers several works.
    """
    if not DOCUMENT_ENGINE.available():
        return {"available": False, "kind": "document", "lines": [], "fields": {},
                "work_refs": [], "note": "Document reading is unavailable on this machine."}
    began = time.time()
    try:
        converted = DOCUMENT_ENGINE.convert(Path(path))
    except Exception as exc:
        return {"available": True, "kind": "document", "lines": [], "fields": {},
                "work_refs": [], "error": f"could not read this document: {exc}"[:300]}
    lines = converted["lines"]
    return {
        "available": True,
        "kind": "document",
        "engine": DOCUMENT_ENGINE.name,
        "engine_label": DOCUMENT_ENGINE.label,
        "seconds": round(time.time() - began, 2),
        "pages": converted["pages"],
        "markdown": converted["markdown"],
        "lines": lines,
        "fields": _extract_fields(lines),
        "work_refs": _all_refs(lines),
        "amounts": _all_amounts(lines),
        "note": "Text read from the document. It has not been verified against any record — "
                "confirm or correct each field before relying on it.",
    }


# ================================================================================ matching


def near_misses(ref: str, known_refs: set[str], limit: int = 4) -> list[str]:
    """Known references one character away from what was read.

    OCR confidence is confidence in the *pixels*, not in the answer. A weathered board can
    return a single wrong digit at 99% confidence, and a reference that is wrong by one
    digit points at a different work just as firmly as one that is wrong by ten. So when a
    read reference is not in the portfolio, we say which real references it almost is, and
    let the officer pick. Exhaustive over single-digit substitutions: about 130 set
    lookups, which is free.
    """
    candidates = []
    for position, character in enumerate(ref):
        if not character.isdigit():
            continue
        for digit in "0123456789":
            if digit == character:
                continue
            candidate = ref[:position] + digit + ref[position + 1:]
            if candidate in known_refs:
                candidates.append(candidate)
    return sorted(set(candidates))[:limit]


def match_to_work(extracted: dict, known_refs: set[str],
                  amounts: dict[str, float] | None = None) -> dict:
    """Decide which work a photographed board belongs to — and how sure that is.

    The failure this is built around is not the unreadable board; it is the *readable* one.
    A weathered board returns "…W136963" at 99.6% character confidence when the board said
    "…W136962", and both are real works — two gym installations at two schools in the same
    block, with the same sanctioned amount. Character confidence cannot separate them and
    neither can the amount.

    So a match is never presented as settled. Every real reference one character away is
    returned alongside it, where the board also carries an amount it is checked against the
    record, and where a second reader read the photograph its reading is compared. The
    officer confirms; the machine narrows.
    """
    field = extracted.get("fields", {}).get("work_ref")
    if not field:
        return {"matched": False, "needs_confirmation": True,
                "reason": "no work reference found in the image"}

    ref = field["value"]
    alternatives = near_misses(ref, known_refs)
    check = extracted.get("cross_check") or {}
    other = check.get("work_ref")
    disagree = bool(other) and other != ref
    if disagree and other in known_refs and other not in alternatives:
        alternatives = sorted(set(alternatives) | {other})[:5]

    result: dict = {
        "work_ref": ref,
        "confidence": field.get("confidence"),
        "alternatives": alternatives,
    }
    if check:
        result["readers_agree"] = check.get("agrees")

    if ref not in known_refs:
        reason = f"{ref} was read from the image but is not a work in this dataset"
        if alternatives:
            reason += (". These real works differ from it by one character: "
                       + ", ".join(alternatives))
        return {**result, "matched": False, "needs_confirmation": True, "reason": reason}

    result["matched"] = True

    board_amount = (extracted.get("fields", {}).get("amount") or {}).get("value")
    on_record = (amounts or {}).get(ref)
    if board_amount and on_record:
        # Cast out of numpy — this dict is serialised to JSON and numpy scalars are not.
        board_amount, on_record = float(board_amount), float(on_record)
        # 1% tolerance: boards are painted with rounded figures.
        agrees = abs(board_amount - on_record) <= max(on_record * 0.01, 1.0)
        result["corroboration"] = {
            "amount_on_board": board_amount,
            "amount_on_record": on_record,
            "agrees": bool(agrees),
        }

    ambiguous = bool(alternatives)
    result["needs_confirmation"] = ambiguous or disagree or not result.get(
        "corroboration", {"agrees": True}
    )["agrees"]
    if disagree:
        result["reason"] = (
            f"The two readers disagree: {extracted.get('engine_label', 'the first reader')} "
            f"read {ref}, {check.get('engine_label', 'the second reader')} read {other}. "
            "Check the board and confirm which one it says."
        )
    elif ambiguous:
        result["reason"] = (
            "Matched, but " + ", ".join(alternatives) + " differ by one character and are "
            "also real works. Character confidence cannot tell them apart — confirm which "
            "board you photographed."
        )
    return result
