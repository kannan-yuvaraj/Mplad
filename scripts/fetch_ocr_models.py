"""Fetch the Surya OCR model and verify it before the API is allowed to use it.

    .venv/Scripts/python.exe scripts/fetch_ocr_models.py            # download + verify
    .venv/Scripts/python.exe scripts/fetch_ocr_models.py --verify   # verify only

Surya reads site photographs with a vision-language model (`datalab-to/surya-ocr-2-gguf`:
the model and its vision projector, about 1.5 GB together) that llama.cpp loads. This
script puts both files in `config.SURYA_GGUF_DIR` and writes `manifest.json` beside them
with each file's size and SHA-256, checked against what Hugging Face publishes.

Why a manifest rather than "the file exists": a download that stopped halfway leaves a
file that exists, has a valid header, and makes llama-server fail forty seconds into
startup. `ocr._Surya` only reports itself available when the manifest says the files are
complete, so a half-finished download means "use RapidOCR for now", never a crash.

Downloads resume: re-running after an interruption continues where it stopped. Files are
written as `<name>.part` and renamed only once verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mplads import config  # noqa: E402

REPO = "datalab-to/surya-ocr-2-gguf"
FILES = (config.SURYA_GGUF_MMPROJ.name, config.SURYA_GGUF_MODEL.name)
MANIFEST = config.SURYA_GGUF_DIR / "manifest.json"
CHUNK = 1 << 20


def published(filename: str) -> dict:
    """Size and SHA-256 of one file as Hugging Face publishes it."""
    from huggingface_hub import HfApi

    info = HfApi().model_info(REPO, files_metadata=True)
    for sibling in info.siblings:
        if sibling.rfilename == filename:
            lfs = sibling.lfs
            sha = getattr(lfs, "sha256", None) if lfs is not None else None
            if sha is None and isinstance(lfs, dict):
                sha = lfs.get("sha256")
            return {"size": sibling.size, "sha256": sha}
    raise SystemExit(f"{filename} is not in {REPO}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(filename: str, expected_size: int) -> Path:
    """Resumable HTTP download to <name>.part; returns the .part path when complete."""
    final = config.SURYA_GGUF_DIR / filename
    part = final.with_name(final.name + ".part")
    if final.exists() and not part.exists():
        # A file left by an earlier, unverified download: resume from it.
        final.rename(part)
    url = f"https://huggingface.co/{REPO}/resolve/main/{filename}"
    for attempt in range(1, 31):
        have = part.stat().st_size if part.exists() else 0
        if have >= expected_size:
            return part
        request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, part.open("ab") as out:
                began, done = time.time(), 0
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if done % (64 * CHUNK) < CHUNK:
                        rate = done / max(time.time() - began, 1e-6)
                        total = have + done
                        print(f"  {filename}: {total / 1e6:,.0f} / {expected_size / 1e6:,.0f} MB"
                              f" ({rate / 1e3:,.0f} KB/s)", flush=True)
        except Exception as exc:  # network drops are expected on slow links; resume
            print(f"  {filename}: attempt {attempt} interrupted ({exc}); resuming", flush=True)
            time.sleep(min(5 * attempt, 60))
    raise SystemExit(f"{filename}: gave up after 30 attempts")


def verify(write: bool) -> bool:
    """Check both files against Hugging Face; write the manifest when they match."""
    entries, ok = {}, True
    for filename in FILES:
        path = config.SURYA_GGUF_DIR / filename
        want = published(filename)
        if not path.is_file():
            print(f"MISSING  {filename}")
            ok = False
            continue
        size = path.stat().st_size
        if size != want["size"]:
            print(f"SIZE     {filename}: {size:,} bytes, expected {want['size']:,}")
            ok = False
            continue
        digest = sha256_of(path)
        if want["sha256"] and digest != want["sha256"]:
            print(f"SHA256   {filename}: {digest} != {want['sha256']}")
            ok = False
            continue
        print(f"OK       {filename}: {size / 1e6:,.1f} MB, sha256 {digest[:16]}…")
        entries[filename] = {"size": size, "sha256": digest}
    if ok and write:
        MANIFEST.write_text(json.dumps({"repo": REPO, "files": entries}, indent=2),
                            encoding="utf-8")
        print(f"wrote {MANIFEST}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="only verify what is on disk")
    args = parser.parse_args()
    config.SURYA_GGUF_DIR.mkdir(parents=True, exist_ok=True)

    if not args.verify:
        for filename in FILES:
            want = published(filename)
            final = config.SURYA_GGUF_DIR / filename
            if final.exists() and final.stat().st_size == want["size"]:
                print(f"present  {filename}")
                continue
            part = download(filename, want["size"])
            part.replace(final)
    sys.exit(0 if verify(write=True) else 1)


if __name__ == "__main__":
    main()
