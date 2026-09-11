"""Phase 7 — image metadata.

Records dimensions, MIME type, size and hash for every downloaded image, and
whatever timestamp the file's own EXIF carries.

**No stage is inferred.** The user brief asks for BEFORE / DURING / AFTER /
COMPLETED where the source identifies it. The portal does not: it exposes a
numeric stage FLAG on the attachment listing and a filename chosen by the
uploading agency. `wc.jpg` on the sample work is in fact a scanned completion
certificate, not a photograph of the asset — so filename-based staging would
have been wrong on the very first file we retrieved. `source_declared_stage`
stays None unless the portal says otherwise; `stage_flag` records what it
actually said.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from ingestion import config
from ingestion.storage.manifest import ManifestWriter, RawStore

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    attach_id: str
    work_recommendation_dtl_id: str
    file_name: str
    stored_path: str
    source_url: str
    stage_flag: int | None
    #: Only ever set from something the source explicitly says. Never inferred.
    source_declared_stage: str | None
    width: int | None
    height: int | None
    mime_type: str | None
    file_size: int
    sha256: str
    retrieved_at: str
    exif_datetime: str | None
    note: str | None


def run_image_inspection() -> dict[str, Any]:
    config.ensure_dirs()
    store = RawStore()
    manifest = ManifestWriter(config.MANIFEST_ROOT / "manifest.jsonl")

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        log.error("Pillow is not available; cannot read image dimensions")
        Image = None  # type: ignore[assignment]

    records: list[ImageMetadata] = []
    for entry in manifest.read():
        if entry.artefact_kind != "image":
            continue
        source = config.DATA_ROOT / entry.stored_path
        if not source.exists():
            continue

        width = height = None
        mime = entry.content_type
        exif_dt = None
        note = entry.note

        if Image is not None:
            try:
                with Image.open(source) as img:
                    width, height = img.size
                    mime = Image.MIME.get(img.format, mime)
                    exif = img.getexif()
                    # 306 = DateTime, 36867 = DateTimeOriginal
                    exif_dt = exif.get(36867) or exif.get(306)
            except (UnidentifiedImageError, OSError) as exc:
                note = f"{note + '; ' if note else ''}Pillow could not open: {exc}"

        records.append(ImageMetadata(
            attach_id=str(entry.identifiers.get("ATTACH_ID", "")),
            work_recommendation_dtl_id=str(entry.identifiers.get("WORK_RECOMMENDATION_DTL_ID", "")),
            file_name=str(entry.identifiers.get("FILE_NAME", "")),
            stored_path=entry.stored_path,
            source_url=entry.source_url,
            stage_flag=entry.identifiers.get("FLAG"),
            source_declared_stage=None,
            width=width, height=height, mime_type=mime,
            file_size=entry.file_size, sha256=entry.sha256,
            retrieved_at=entry.retrieved_at,
            exif_datetime=str(exif_dt) if exif_dt else None,
            note=note,
        ))

    summary = {
        "images": len(records),
        "with_dimensions": sum(1 for r in records if r.width),
        "with_exif_datetime": sum(1 for r in records if r.exif_datetime),
        "stage_labelled_by_source": 0,
        "stage_note": ("The portal exposes no BEFORE/DURING/AFTER label. "
                       "source_declared_stage is None on every record by design."),
        "detail": [asdict(r) for r in records],
    }
    store.write_json(obj=summary, destination=config.REPORT_ROOT / "image_metadata.json",
                     source_url="(derived)", artefact_kind="api", http_status=200,
                     http_method="LOCAL")
    return summary
