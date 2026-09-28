"""In-memory sync progress for UI toasts (single-user local app)."""
from __future__ import annotations

import threading
import time
from typing import Any

# A sync with no progress for this long is treated as wedged rather than
# leaving the UI on a spinner forever.
STALL_AFTER_S = 300

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "account_id": None,
    "account_name": None,
    "phase": "idle",
    "current": 0,
    "total": 0,
    "message": "",
}
_last_update: float = 0.0


def _touch() -> None:
    global _last_update
    _last_update = time.monotonic()


def get() -> dict[str, Any]:
    with _lock:
        state = dict(_state)
        if state["running"]:
            idle_for = time.monotonic() - _last_update
            state["stalled"] = idle_for > STALL_AFTER_S
            state["idle_seconds"] = int(idle_for)
        else:
            state["stalled"] = False
            state["idle_seconds"] = 0
        return state


def is_stalled() -> bool:
    with _lock:
        if not _state["running"]:
            return False
        return (time.monotonic() - _last_update) > STALL_AFTER_S


def start(account_id: int, account_name: str, total: int) -> None:
    with _lock:
        _state.update(
            {
                "running": True,
                "account_id": account_id,
                "account_name": account_name,
                "phase": "fetching",
                "current": 0,
                "total": total,
                "message": f"Fetched {total} email(s)…",
            }
        )
        _touch()


def tick(current: int, *, subject: str | None = None) -> None:
    with _lock:
        _state["phase"] = "analyzing"
        _state["current"] = current
        total = _state.get("total") or 0
        label = f"Analyzing {current}/{total}"
        if subject:
            label += f": {subject[:60]}"
        _state["message"] = label
        _touch()


def finish(message: str = "Sync complete") -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "done",
                "message": message,
            }
        )
        _touch()


def fail(message: str) -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "error",
                "message": message,
            }
        )
        _touch()


def release() -> None:
    """Clear a running flag left behind by a crashed sync."""
    with _lock:
        if _state["running"]:
            _state.update(
                {
                    "running": False,
                    "phase": "error",
                    "message": "Sync stopped unexpectedly. Try Sync Now again.",
                }
            )
            _touch()
