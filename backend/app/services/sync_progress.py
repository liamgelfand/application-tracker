"""In-memory sync progress for UI toasts (single-user local app)."""
from __future__ import annotations

import threading
from typing import Any

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


def get() -> dict[str, Any]:
    with _lock:
        return dict(_state)


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


def tick(current: int, *, subject: str | None = None) -> None:
    with _lock:
        _state["phase"] = "analyzing"
        _state["current"] = current
        total = _state.get("total") or 0
        label = f"Analyzing {current}/{total}"
        if subject:
            label += f": {subject[:60]}"
        _state["message"] = label


def finish(message: str = "Sync complete") -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "done",
                "message": message,
            }
        )


def fail(message: str) -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "error",
                "message": message,
            }
        )
