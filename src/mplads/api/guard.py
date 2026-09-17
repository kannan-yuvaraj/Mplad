"""Load guards for the endpoints that read photographs and documents.

The deployment is one worker on a 512 MB, 0.1-CPU container, and it serves a
public link. Three things measured or read off that shape, each of which could
take the whole site down with ordinary traffic rather than an attack:

* **Reading blocked the event loop.** `/api/ocr` was `async def` and called the
  reader directly. While one photograph was read, every other request — the
  health check included — waited: 19.9 s for `/api/health` against 0.04 s idle.
  On the host, a health check that slow gets the service restarted. The heavy
  call now runs in a worker thread (`run_heavy`).
* **Uploads were read whole before the size check.** `await file.read()` then
  `len(data) > cap` means a 400 MB upload is in memory before it is refused, on
  a container that has 512 MB. `read_capped` stops at the cap.
* **Nothing bounded concurrency.** Two readers at once is two models' worth of
  memory. `heavy_slot` admits a fixed number and answers the rest with 429 and a
  `Retry-After`, rather than queueing work the container cannot hold.

A per-client rate limit sits on top. It keys on the first `X-Forwarded-For` hop
because the host's proxy sets it; that header can be forged, so the limit is a
courtesy against accidental hammering, and the slot count is the real guard.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

from fastapi import HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from mplads import config

T = TypeVar("T")

#: How many photographs or documents may be read at the same moment.
MAX_CONCURRENT_HEAVY = 1 if config.LOW_MEMORY else 2

#: Per client, per window.
HEAVY_REQUESTS_PER_WINDOW = 8
LOGIN_ATTEMPTS_PER_WINDOW = 10
WINDOW_SECONDS = 60

_CHUNK = 1024 * 1024

_slots = threading.BoundedSemaphore(MAX_CONCURRENT_HEAVY)
_hits: dict[tuple[str, str], deque[float]] = {}
_hits_lock = threading.Lock()


async def read_capped(file: UploadFile, cap: int, what: str) -> bytes:
    """Read an upload, refusing it as soon as it passes `cap` bytes."""
    parts: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > cap:
            raise HTTPException(413, f"{what} is larger than {cap // _CHUNK} MB")
        parts.append(chunk)
    if not size:
        raise HTTPException(400, f"the uploaded {what} is empty")
    return b"".join(parts)


def try_acquire_slot() -> bool:
    """Take a reading slot without waiting. The caller must `release_slot()`."""
    return _slots.acquire(blocking=False)


def release_slot() -> None:
    _slots.release()


def busy() -> HTTPException:
    return HTTPException(
        429,
        "The service is already reading another upload. Try again in a few seconds.",
        headers={"Retry-After": "10"},
    )


@contextmanager
def heavy_slot() -> Iterator[None]:
    """Hold one reading slot for the duration of the block, or refuse with 429."""
    if not try_acquire_slot():
        raise busy()
    try:
        yield
    finally:
        release_slot()


async def run_heavy(fn: Callable[..., T], *args, **kwargs) -> T:
    """Run blocking work off the event loop so other requests keep being served."""
    return await run_in_threadpool(fn, *args, **kwargs)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, bucket: str, limit: int,
               window: float = WINDOW_SECONDS) -> None:
    """Sliding-window limit per client and bucket. Raises 429 when exceeded."""
    now = time.monotonic()
    key = (bucket, client_key(request))
    with _hits_lock:
        hits = _hits.setdefault(key, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(window - (now - hits[0])) + 1)
            raise HTTPException(
                429, "Too many requests from this address. Wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)
        # Forget clients that have gone quiet, so the table cannot grow without bound.
        if len(_hits) > 5000:
            for stale in [k for k, v in _hits.items() if not v or now - v[-1] > window]:
                del _hits[stale]


def reset() -> None:
    """Clear rate-limit history. For tests."""
    with _hits_lock:
        _hits.clear()
