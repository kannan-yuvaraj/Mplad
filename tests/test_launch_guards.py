"""The guards added before the public launch, each pinned on its failure path."""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from mplads import config
from mplads.api import guard, live


def _upload(data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename="x.png")


def _request(ip: str = "203.0.113.7") -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-for", ip.encode())],
                    "client": ("127.0.0.1", 1)})


def test_an_upload_over_the_cap_is_refused_without_reading_it_all():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(guard.read_capped(_upload(b"x" * (3 * 1024 * 1024)), 2 * 1024 * 1024, "image"))
    assert exc.value.status_code == 413


def test_an_empty_upload_is_refused():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(guard.read_capped(_upload(b""), 1024, "image"))
    assert exc.value.status_code == 400


def test_an_upload_under_the_cap_comes_back_whole():
    body = os.urandom(2_500_000)
    assert asyncio.run(guard.read_capped(_upload(body), 3 * 1024 * 1024, "image")) == body


def test_a_full_service_answers_busy_instead_of_queueing():
    taken = [guard.try_acquire_slot() for _ in range(guard.MAX_CONCURRENT_HEAVY)]
    try:
        assert all(taken)
        with pytest.raises(HTTPException) as exc:
            with guard.heavy_slot():
                pass
        assert exc.value.status_code == 429
        assert exc.value.headers["Retry-After"]
    finally:
        for _ in taken:
            guard.release_slot()
    with guard.heavy_slot():  # released: admits again
        pass


def test_rate_limit_refuses_past_the_limit_and_only_for_that_client():
    guard.reset()
    for _ in range(3):
        guard.rate_limit(_request("198.51.100.1"), "test", 3)
    with pytest.raises(HTTPException) as exc:
        guard.rate_limit(_request("198.51.100.1"), "test", 3)
    assert exc.value.status_code == 429
    guard.rate_limit(_request("198.51.100.2"), "test", 3)  # someone else is unaffected
    guard.reset()


def test_without_a_configured_secret_tokens_are_not_signed_with_a_published_one():
    env = {k: v for k, v in os.environ.items() if k != "MPLADS_JWT_SECRET"}
    code = ("from mplads import config; "
            "print(config.JWT_SECRET_IS_EPHEMERAL, len(config.JWT_SECRET), "
            "config.JWT_SECRET == 'dev-only-not-a-production-secret')")
    # Run where no .env can supply the variable.
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         text=True, cwd=str(config.REPO_ROOT / "tests"), check=False)
    if (config.REPO_ROOT / ".env").exists() and "MPLADS_JWT_SECRET" in (
            config.REPO_ROOT / ".env").read_text(encoding="utf-8", errors="ignore"):
        pytest.skip(".env sets MPLADS_JWT_SECRET on this machine")
    assert out.returncode == 0, out.stderr
    ephemeral, length, published = out.stdout.split()
    assert ephemeral == "True" and int(length) >= 64 and published == "False"


def test_vendor_screen_falls_back_to_the_saved_copy_and_says_so(monkeypatch):
    if not live.VENDOR_SNAPSHOT.exists():
        pytest.skip("no vendor snapshot in this checkout")
    monkeypatch.setattr(live, "_store", lambda: None)
    body = live.vendor_concentration(limit=5, band=None)
    assert body["available"] is True
    assert body["source"] == "snapshot"
    assert body["snapshot_taken_at"]
    assert len(body["authorities"]) <= 5
