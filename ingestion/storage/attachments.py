"""Attachment retrieval shared by the document and image downloaders.

The portal does not serve attachments over a file URL. It returns them as
base64 inside a JSON body, with no content type, so this module is responsible
for deciding what a file actually *is* before it writes it:

- the extension from the server-supplied filename is a claim, not evidence;
- the magic bytes are checked against that claim and any disagreement is
  recorded on the manifest entry rather than silently corrected;
- a file whose declared extension we do not recognise is still stored, under
  `unknown/`, because discarding public evidence is worse than storing it.

Nothing here infers a photograph's stage. The portal exposes a stage FLAG and a
filename; neither reliably says BEFORE/DURING/AFTER, so we record the FLAG and
stop. See `ingestion/research/LIMITATIONS.md`.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ingestion import api, config
from ingestion.client import PortalClient, PortalError
from ingestion.storage.manifest import ManifestEntry, RawStore

log = logging.getLogger(__name__)

#: Magic-byte signatures we can confirm. Anything absent from this table is
#: stored without a confirmation, and the manifest says so.
MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/zip (docx/xlsx family)",
    b"\xd0\xcf\x11\xe0": "application/msword (OLE2)",
    b"BM": "image/bmp",
}


def sniff(payload: bytes) -> str | None:
    """Identify a payload by its magic bytes, or None if unrecognised."""
    for signature, mime in MAGIC.items():
        if payload.startswith(signature):
            return mime
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


def classify(filename: str) -> str:
    """`image`, `document`, or `unknown` — from the declared extension."""
    suffix = Path(filename).suffix.lower()
    if suffix in config.IMAGE_EXTENSIONS:
        return "image"
    if suffix in config.DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


@dataclass(frozen=True, slots=True)
class AttachmentRef:
    """One publicly listed attachment, before retrieval."""

    work_recommendation_dtl_id: str
    flag: int
    attach_id: str
    file_name: str

    @property
    def kind(self) -> str:
        return classify(self.file_name)


@dataclass(frozen=True, slots=True)
class AttachmentFailure:
    """A listed attachment we could not retrieve. Never silently dropped."""

    ref: AttachmentRef
    http_status: int | None
    error: str
    retry_count: int


def enumerate_attachments(
    client: PortalClient,
    work_recommendation_dtl_id: int | str,
    *,
    store: RawStore | None = None,
    flags: tuple[int, ...] = config.ATTACHMENT_FLAGS,
) -> list[AttachmentRef]:
    """List every attachment the portal exposes for a work, across stage FLAGs.

    Deduplicates by `attach_id`: the same file is returned under more than one
    FLAG for some works, and we want one copy with the FLAGs recorded.
    """
    work_id = str(work_recommendation_dtl_id)
    seen: dict[str, AttachmentRef] = {}

    for flag in flags:
        try:
            body, raw = api.list_attachments(client, work_id, flag)
        except PortalError as exc:
            log.warning("attachment listing failed for work %s flag %s: %s", work_id, flag, exc)
            continue

        if store is not None:
            store.write(
                payload=raw.content,
                destination=config.RAW_API / "attachments" / work_id / f"flag_{flag}.json",
                source_url=raw.url,
                request_body=raw.request_body,
                artefact_kind="api",
                http_status=raw.status_code,
                content_type=raw.content_type,
                identifiers={"WORK_RECOMMENDATION_DTL_ID": work_id, "FLAG": flag},
            )

        for record in body if isinstance(body, list) else []:
            names = record.get("FILE_NAME")
            ids = record.get("ATTACH_ID")
            # Sentinel: the stage exists but carries no file.
            if names == config.ATTACHMENT_ABSENT or not isinstance(names, list):
                continue
            if not isinstance(ids, list) or len(ids) != len(names):
                log.warning("work %s flag %s: %d names but %s ids — skipped",
                            work_id, flag, len(names), "no" if ids is None else len(ids))
                continue
            for name, attach_id in zip(names, ids):
                if name == "File not available.":
                    continue
                seen.setdefault(
                    str(attach_id),
                    AttachmentRef(work_id, flag, str(attach_id), str(name)),
                )

    return list(seen.values())


def download_attachment(
    client: PortalClient,
    ref: AttachmentRef,
    store: RawStore,
    *,
    known_hashes: set[str] | None = None,
) -> ManifestEntry | AttachmentFailure:
    """Retrieve one attachment, verify it, store it, manifest it.

    Returns a `ManifestEntry` on success or an `AttachmentFailure` on failure.
    Failures are returned, never raised and never swallowed, so the completeness
    report can list every one of them.
    """
    try:
        record, raw = api.get_attachment(client, ref.attach_id)
    except PortalError as exc:
        return AttachmentFailure(ref, exc.status, exc.detail, client.retry_count)

    b64 = record.get("URL")
    if not b64:
        return AttachmentFailure(ref, raw.status_code, "response carried no URL field", 0)

    try:
        payload = base64.b64decode(b64)
    except (binascii.Error, ValueError) as exc:
        return AttachmentFailure(ref, raw.status_code, f"base64 decode failed: {exc}", 0)

    if not payload:
        return AttachmentFailure(ref, raw.status_code, "decoded to zero bytes", 0)

    sniffed = sniff(payload)
    declared = Path(ref.file_name).suffix.lower().lstrip(".")
    note = None
    if sniffed is None:
        note = f"magic bytes unrecognised; extension claims .{declared}"
    elif declared and declared not in sniffed and not (
        declared in {"jpg", "jpeg"} and sniffed == "image/jpeg"
    ):
        note = f"extension claims .{declared} but magic bytes say {sniffed}"

    kind = ref.kind
    root = {"image": config.RAW_IMAGES, "document": config.RAW_DOCUMENTS}.get(
        kind, config.RAW_ROOT / "unknown"
    )
    safe_name = Path(ref.file_name).name.replace("/", "_").replace("\\", "_")
    destination = root / ref.work_recommendation_dtl_id / f"{ref.attach_id}__{safe_name}"

    entry = store.write(
        payload=payload,
        destination=destination,
        source_url=raw.url,
        request_body=raw.request_body,
        artefact_kind=kind,
        http_status=raw.status_code,
        content_type=sniffed,
        identifiers={
            "WORK_RECOMMENDATION_DTL_ID": ref.work_recommendation_dtl_id,
            "ATTACH_ID": ref.attach_id,
            "ATTACH_PARENT_ID": ref.attach_id.split(".")[0],
            "FLAG": ref.flag,
            "FILE_NAME": ref.file_name,
            "declared_extension": declared,
        },
        note=note,
    )

    if known_hashes is not None:
        if entry.sha256 in known_hashes:
            log.info("duplicate content: %s matches an already-stored file", ref.attach_id)
        known_hashes.add(entry.sha256)

    return entry


def iter_attachment_refs(rows: list[dict[str, Any]]) -> Iterator[tuple[str, int]]:
    """(work_recommendation_dtl_id, FLAG) pairs worth asking about, from work rows.

    Only rows that actually carry an `ATTACH_ID` are yielded — a work with a
    null `ATTACH_ID` has nothing to enumerate and asking would waste a request
    against the portal.
    """
    for row in rows:
        work_id = row.get("WORK_RECOMMENDATION_DTL_ID")
        if work_id is None or row.get("ATTACH_ID") in (None, "", 0):
            continue
        flag = row.get("FLAG")
        yield str(work_id), int(flag) if isinstance(flag, (int, float)) else 1
