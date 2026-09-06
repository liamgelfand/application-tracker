from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import ApplicationStatus, Setting

AUTO_APPLY_KEY = "auto_apply_suggestions"
POLL_INTERVAL_KEY = "email_poll_interval_seconds"
MIN_CONFIDENCE_KEY = "min_suggestion_confidence"
FOLLOW_UP_DAYS_KEY = "follow_up_days"
HIDDEN_BOARD_KEY = "hidden_board_statuses"

MIN_POLL_INTERVAL = 60
MAX_POLL_INTERVAL = 86400
DEFAULT_MIN_CONFIDENCE = 70
DEFAULT_FOLLOW_UP_DAYS = 14
DEFAULT_HIDDEN_BOARD_STATUSES = [
    ApplicationStatus.phone_screen,
    ApplicationStatus.rejected,
    ApplicationStatus.ghosted,
]


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def get_auto_apply(db: Session) -> bool:
    return get_setting(db, AUTO_APPLY_KEY, "false") == "true"


def set_auto_apply(db: Session, value: bool) -> None:
    set_setting(db, AUTO_APPLY_KEY, "true" if value else "false")


def get_poll_interval(db: Session, default: int) -> int:
    raw = get_setting(db, POLL_INTERVAL_KEY)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def set_poll_interval(db: Session, seconds: int) -> int:
    seconds = max(MIN_POLL_INTERVAL, min(MAX_POLL_INTERVAL, int(seconds)))
    set_setting(db, POLL_INTERVAL_KEY, str(seconds))
    return seconds


def get_min_confidence(db: Session, default: int = DEFAULT_MIN_CONFIDENCE) -> int:
    raw = get_setting(db, MIN_CONFIDENCE_KEY)
    if raw is None:
        return default
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return default


def set_min_confidence(db: Session, value: int) -> int:
    value = max(0, min(100, int(value)))
    set_setting(db, MIN_CONFIDENCE_KEY, str(value))
    return value


def get_follow_up_days(db: Session, default: int = DEFAULT_FOLLOW_UP_DAYS) -> int:
    raw = get_setting(db, FOLLOW_UP_DAYS_KEY)
    if raw is None:
        return default
    try:
        return max(1, min(365, int(raw)))
    except ValueError:
        return default


def set_follow_up_days(db: Session, value: int) -> int:
    value = max(1, min(365, int(value)))
    set_setting(db, FOLLOW_UP_DAYS_KEY, str(value))
    return value


def _ordered_statuses(statuses: list[ApplicationStatus]) -> list[ApplicationStatus]:
    wanted = set(statuses)
    return [s for s in ApplicationStatus if s in wanted]


def get_hidden_board_statuses(db: Session) -> list[ApplicationStatus]:
    raw = get_setting(db, HIDDEN_BOARD_KEY)
    if raw is None:
        return list(DEFAULT_HIDDEN_BOARD_STATUSES)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return list(DEFAULT_HIDDEN_BOARD_STATUSES)
    if not isinstance(data, list):
        return list(DEFAULT_HIDDEN_BOARD_STATUSES)
    parsed: list[ApplicationStatus] = []
    for item in data:
        try:
            parsed.append(ApplicationStatus(item))
        except ValueError:
            continue
    return _ordered_statuses(parsed)


def set_hidden_board_statuses(
    db: Session, statuses: list[ApplicationStatus]
) -> list[ApplicationStatus]:
    unique = _ordered_statuses(list(dict.fromkeys(statuses)))
    if len(unique) >= len(ApplicationStatus):
        raise ValueError("At least one status must stay visible on the board")
    set_setting(db, HIDDEN_BOARD_KEY, json.dumps([s.value for s in unique]))
    return unique
