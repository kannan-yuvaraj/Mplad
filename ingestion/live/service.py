"""The long-running sync service.

Runs `sync_once` on a fast cadence and `sync_full` on a slow one, forever, and
survives everything it reasonably can: a portal outage, a malformed response, a
machine that sleeps, a kill -9 between cycles.

**Design decisions that matter more than they look:**

- **One cycle can never kill the loop.** `sync_once` already catches per-cycle
  failures; the loop additionally backs off when cycles fail consecutively, so a
  portal that is down for an hour is not hammered 60 times.
- **The interval is the floor, not the period.** If a cycle takes 4 minutes and
  the interval is 5, the next starts a minute later — not immediately, and not
  4 minutes late and drifting.
- **A single instance.** A lock file holds the PID so two schedulers cannot poll
  the same portal at twice the agreed rate. Politeness is not enforceable if any
  number of copies can run.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ingestion.live.store import LIVE_ROOT, LiveStore
from ingestion.live.sync import sync_full, sync_once
from ingestion.storage.manifest import utc_now_iso

log = logging.getLogger(__name__)

LOCK_PATH = LIVE_ROOT / "scheduler.lock"
HEARTBEAT_PATH = LIVE_ROOT / "heartbeat.json"

#: Defaults. The fast cadence is what bounds how stale the site can be; the full
#: sweep is the safety net for changes that do not move a scope's totals.
DEFAULT_INTERVAL_SECONDS = 900          # 15 minutes
DEFAULT_FULL_EVERY_SECONDS = 86_400     # nightly

MAX_BACKOFF_SECONDS = 1_800


@dataclass
class ServiceState:
    cycles: int = 0
    failures_in_a_row: int = 0
    last_ok_at: str | None = None
    last_full_at: float = 0.0
    stopping: bool = False


class SingleInstanceLock:
    """Refuse to start a second scheduler against the same portal."""

    def __init__(self, path: Path = LOCK_PATH) -> None:
        self.path = path
        self.acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                blob = json.loads(self.path.read_text(encoding="utf-8"))
                pid = int(blob.get("pid", -1))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pid = -1
            if pid > 0 and _pid_alive(pid):
                raise RuntimeError(
                    f"a live scheduler is already running (pid {pid}). "
                    f"Stop it, or delete {self.path} if it is stale."
                )
            log.warning("removing stale lock from pid %s", pid)

        self.path.write_text(
            json.dumps({"pid": os.getpid(), "started_at": utc_now_iso()}),
            encoding="utf-8",
        )
        self.acquired = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import subprocess
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return str(pid) in out
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _write_heartbeat(state: ServiceState, last_result: dict[str, Any] | None,
                     next_run_at: float) -> None:
    """A file anything can read to answer 'is the feed alive?'.

    Deliberately a file rather than a process query: the API serves this without
    needing to find, signal or trust the scheduler process.
    """
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(json.dumps({
        "pid": os.getpid(),
        "updated_at": utc_now_iso(),
        "cycles": state.cycles,
        "failures_in_a_row": state.failures_in_a_row,
        "last_ok_at": state.last_ok_at,
        "next_run_in_seconds": max(0, round(next_run_at - time.monotonic())),
        "last_result": last_result,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def run_service(*, interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
                full_every_seconds: float = DEFAULT_FULL_EVERY_SECONDS,
                max_cycles: int | None = None) -> dict[str, Any]:
    """Poll forever (or for `max_cycles`, which exists so tests can run it)."""
    state = ServiceState()
    store = LiveStore()

    def _stop(signum: int, _frame: object) -> None:
        log.info("signal %s received — finishing the current cycle then stopping", signum)
        state.stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            pass  # not the main thread, or unsupported on this platform

    with SingleInstanceLock():
        log.info("live sync service started: every %.0fs, full sweep every %.0fs",
                 interval_seconds, full_every_seconds)
        last_result: dict[str, Any] | None = None

        while not state.stopping:
            started = time.monotonic()
            due_for_full = (started - state.last_full_at) >= full_every_seconds

            try:
                if due_for_full:
                    last_result = sync_full(store=store)
                    state.last_full_at = started
                else:
                    last_result = sync_once(store=store)
            except Exception as exc:  # the loop outlives any single failure
                log.exception("cycle raised")
                last_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

            state.cycles += 1
            if last_result.get("ok"):
                state.failures_in_a_row = 0
                state.last_ok_at = utc_now_iso()
            else:
                state.failures_in_a_row += 1

            # Back off when the portal is unwell rather than retrying at full rate.
            wait = interval_seconds
            if state.failures_in_a_row:
                wait = min(interval_seconds * (2 ** state.failures_in_a_row),
                           MAX_BACKOFF_SECONDS)
                log.warning("%d consecutive failures — next cycle in %.0fs",
                            state.failures_in_a_row, wait)

            elapsed = time.monotonic() - started
            sleep_for = max(0.0, wait - elapsed)
            next_run_at = time.monotonic() + sleep_for
            _write_heartbeat(state, last_result, next_run_at)

            if max_cycles is not None and state.cycles >= max_cycles:
                break
            if state.stopping:
                break

            # Sleep in slices so a signal is noticed promptly.
            deadline = time.monotonic() + sleep_for
            while time.monotonic() < deadline and not state.stopping:
                time.sleep(min(2.0, deadline - time.monotonic()))

    log.info("live sync service stopped after %d cycles", state.cycles)
    return {
        "cycles": state.cycles,
        "last_ok_at": state.last_ok_at,
        "failures_in_a_row": state.failures_in_a_row,
        "status": store.status(),
    }


def heartbeat() -> dict[str, Any]:
    """What the API reads to report freshness. Never raises."""
    if not HEARTBEAT_PATH.exists():
        return {"running": False, "reason": "no heartbeat file — the service has never run"}
    try:
        blob = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"running": False, "reason": f"heartbeat unreadable: {exc}"}
    blob["running"] = _pid_alive(int(blob.get("pid", -1)))
    return blob
