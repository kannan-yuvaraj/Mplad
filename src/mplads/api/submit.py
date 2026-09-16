"""The eSAKSHI-style intake endpoint, streamed stage by stage.

`POST /api/submission/assess` takes an uploaded photograph or document exactly as
an Implementing Agency would submit it, and streams the assessment back as
Server-Sent Events — one event per stage, as that stage finishes.

**Streaming is not decoration here.** The stages genuinely take different amounts
of time: OCR is seconds, a portfolio lookup is microseconds. Buffering them into
one response would hide the fact that real work is happening and would make a
fast machine indistinguishable from a canned animation. The client renders the
plan up front and fills it in as events land.

A non-streaming `POST /api/submission/assess-sync` returns the same stages in one
body, for clients that cannot consume SSE and for the tests.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from mplads import submission

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/submission", tags=["submission"])

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


def _assessment(actor: str) -> submission.Assessment:
    """Build an assessment bound to the API's cached portfolio.

    Imported here rather than at module scope because `app` imports this module —
    importing it back at the top would be circular.
    """
    from mplads.api.app import _clear_record, store

    cache = store()

    def lookup(work_ref: str) -> dict | None:
        return cache.cases_by_ref.get(work_ref) or _clear_record(work_ref)

    return submission.Assessment(
        known_refs=cache.all_refs,
        amounts=cache.amounts,
        case_lookup=lookup,
        actor=actor,
    )


async def _read_upload(file: UploadFile, kind: str) -> bytes:
    data = await file.read()
    cap = MAX_PHOTO_BYTES if kind == "photo" else MAX_DOCUMENT_BYTES
    if len(data) > cap:
        raise HTTPException(400, f"file is larger than {cap // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(400, "the uploaded file is empty")
    return data


@router.get("/plan")
def plan() -> dict[str, Any]:
    """The stages, in order, so the UI can draw the whole pipeline before it runs.

    A progress list that grows as results arrive tells the viewer nothing about
    how much is left. Handing over the plan first means the eleven steps are
    visible from the start and simply resolve in place.
    """
    return {
        "stages": [{"stage": s, "title": t} for s, t in submission.STAGE_PLAN],
        "count": len(submission.STAGE_PLAN),
        "readers": _readers(),
        "contract": (
            "This reads one submission and compares it against the portfolio and the "
            "scored snapshot. It does not retrain or re-score anything, and it does not "
            "produce a fraud finding — MPLADS data carries no fraud labels."
        ),
    }


@router.post("/assess")
async def assess_stream(
    file: UploadFile = File(...),
    kind: str = Form("photo"),
    work_ref: str = Form(""),
    amount: str = Form(""),
    reader: str = Form(""),
) -> StreamingResponse:
    """Stream the assessment as Server-Sent Events."""
    if kind not in {"photo", "document"}:
        raise HTTPException(400, "kind must be 'photo' or 'document'")
    data = await _read_upload(file, kind)
    filename = file.filename or ("upload.jpg" if kind == "photo" else "upload.pdf")

    declared_amount: float | None = None
    if amount.strip():
        try:
            declared_amount = float(amount.replace(",", "").strip())
        except ValueError:
            raise HTTPException(400, "amount must be a number")

    engine = _assessment(actor="demo-intake")

    def events() -> Iterator[str]:
        # The plan first, so the client can render all eleven rows immediately.
        yield _sse("plan", {"stages": [{"stage": s, "title": t}
                                       for s, t in submission.STAGE_PLAN]})
        try:
            for stage in engine.run(data=data, filename=filename, kind=kind,
                                    declared_work_ref=work_ref.strip(),
                                    declared_amount=declared_amount,
                                    reader=reader.strip() or None):
                yield _sse("stage", stage.to_dict())
        except Exception as exc:  # a failure must reach the screen, not hang it
            LOGGER.exception("assessment failed")
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})
        yield _sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this an nginx in front of the API buffers the whole stream
            # and every stage arrives at once, which defeats the point.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/assess-sync")
async def assess_sync(
    file: UploadFile = File(...),
    kind: str = Form("photo"),
    work_ref: str = Form(""),
    amount: str = Form(""),
    reader: str = Form(""),
) -> dict[str, Any]:
    """The same assessment, returned in one body."""
    if kind not in {"photo", "document"}:
        raise HTTPException(400, "kind must be 'photo' or 'document'")
    data = await _read_upload(file, kind)
    filename = file.filename or ("upload.jpg" if kind == "photo" else "upload.pdf")

    declared_amount: float | None = None
    if amount.strip():
        try:
            declared_amount = float(amount.replace(",", "").strip())
        except ValueError:
            raise HTTPException(400, "amount must be a number")

    engine = _assessment(actor="demo-intake")
    stages = [s.to_dict() for s in engine.run(
        data=data, filename=filename, kind=kind,
        declared_work_ref=work_ref.strip(), declared_amount=declared_amount,
        reader=reader.strip() or None)]

    lead = next((s for s in reversed(stages) if s["stage"] == "lead"), None)
    return {
        "stages": stages,
        "completed": len(stages),
        "planned": len(submission.STAGE_PLAN),
        "stopped_early": len(stages) < len(submission.STAGE_PLAN),
        "lead": lead,
        "not_a_fraud_finding": True,
    }


def _readers() -> list[dict[str, Any]]:
    """Which photograph readers this machine has, fastest last-known first.

    Reading dominates the wall clock — every other stage finishes in
    milliseconds — so this is the only choice on the page that changes how it
    feels, and the UI states the trade rather than hiding it behind a spinner.
    """
    from mplads import ocr

    # Numbers from this project's own benchmark — scripts/benchmark_ocr.py over 44
    # generated boards in 11 photograph conditions, on the T1000. See
    # docs/OCR_BENCHMARK.md. Synthetic boards, and the doc says so.
    labels = {
        "rapidocr": (
            "Fast — one reader",
            "RapidOCR (PP-OCRv4), ~2 s a board. Benchmark: 91% exact reference, but "
            "only 73% on the amount — it drops the rupee sign — and 0% under motion "
            "blur. Runs alone, so no second reader can disagree with it.",
        ),
        "surya": (
            "Most accurate — two readers",
            "Surya OCR 2, a local vision model on the GPU. ~20 s a board, and up to a "
            "minute on the first read of a session while the model loads. Benchmark: "
            "93% exact reference, 93% on the amount, 50% under motion blur. RapidOCR "
            "reads the same photograph as a check.",
        ),
    }
    out = []
    for name, engine in ocr.ENGINES.items():
        try:
            if not engine.available():
                continue
        except Exception:
            continue
        label, note = labels.get(name, (name, ""))
        out.append({"engine": name, "label": label, "note": note,
                    "engine_label": getattr(engine, "label", name)})
    out.sort(key=lambda r: 0 if r["engine"] == "rapidocr" else 1)
    return out


def _sse(event: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n"
