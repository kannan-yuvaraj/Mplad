"""Throttled, retrying HTTP client for the eSAKSHI public REST API.

Phase 9 is a hard requirement, not a preference: this is a government server.
The client is deliberately single-threaded, sleeps between every request, and
backs off exponentially on failure. There is no concurrency setting.

Every response passes through `PortalClient.post_json`, which returns the parsed
body *and* the raw bytes, so the caller can preserve the original response
(Phase 5) rather than only the transformed data.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ingestion import config

log = logging.getLogger(__name__)


class PortalError(RuntimeError):
    """A request failed after exhausting retries."""

    def __init__(self, path: str, body: Any, status: int | None, detail: str) -> None:
        super().__init__(f"{path} {json.dumps(body)[:160]} -> {status}: {detail}")
        self.path = path
        self.body = body
        self.status = status
        self.detail = detail


@dataclass(slots=True)
class RawResponse:
    """A response and everything needed to prove where it came from."""

    url: str
    request_body: str
    status_code: int
    content_type: str | None
    content: bytes
    elapsed_seconds: float

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class PortalClient:
    """Polite client for `mplads.mospi.gov.in`.

    Usage::

        with PortalClient() as client:
            response = client.post_json("/rest/PreLoginDashboardData/getStateData", {})
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        delay_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or config.BASE_URL).rstrip("/")
        self.delay_seconds = config.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
        self.max_retries = config.MAX_RETRIES if max_retries is None else max_retries
        self._last_request_at = 0.0
        self.request_count = 0
        self.retry_count = 0

        self._client = httpx.Client(
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={
                "User-Agent": config.USER_AGENT,
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                # The frontend sends this on most calls; mirroring it keeps our
                # traffic shaped like the traffic the server expects.
                "X-Client-UA": config.USER_AGENT,
                "Referer": config.DASHBOARD_URL,
                "Origin": self.base_url,
            },
        )

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "PortalClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- throttling --------------------------------------------------------

    def _throttle(self, extra: float = 0.0) -> None:
        target = self.delay_seconds + extra
        waited = time.monotonic() - self._last_request_at
        if waited < target:
            time.sleep(target - waited)
        self._last_request_at = time.monotonic()

    # -- the one request path ---------------------------------------------

    def post_json(
        self,
        path: str,
        body: Any,
        *,
        extra_delay: float = 0.0,
    ) -> RawResponse:
        """POST a JSON body and return the raw response.

        Retries on transport errors and on 5xx/429 with exponential backoff and
        jitter. A 4xx other than 429 is not retried — it means we asked wrongly,
        and hammering will not fix that.
        """
        url = self.base_url + path
        payload = json.dumps(body)
        last_detail = "no attempt made"
        status: int | None = None

        for attempt in range(self.max_retries + 1):
            self._throttle(extra_delay if attempt == 0 else 0.0)
            started = time.monotonic()
            try:
                response = self._client.post(url, content=payload)
                status = response.status_code
                elapsed = time.monotonic() - started
                self.request_count += 1

                if status == 200:
                    return RawResponse(
                        url=url,
                        request_body=payload,
                        status_code=status,
                        content_type=response.headers.get("content-type"),
                        content=response.content,
                        elapsed_seconds=elapsed,
                    )

                if status < 500 and status != 429:
                    raise PortalError(path, body, status, response.text[:200])

                last_detail = f"HTTP {status}"
            except httpx.HTTPError as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
                self.request_count += 1

            if attempt < self.max_retries:
                self.retry_count += 1
                backoff = min(
                    config.BACKOFF_BASE_SECONDS * (2 ** attempt),
                    config.BACKOFF_MAX_SECONDS,
                )
                backoff += random.uniform(0, backoff * 0.25)
                log.warning(
                    "retry %d/%d for %s after %s; sleeping %.1fs",
                    attempt + 1, self.max_retries, path, last_detail, backoff,
                )
                time.sleep(backoff)

        raise PortalError(path, body, status, f"exhausted {self.max_retries} retries: {last_detail}")
