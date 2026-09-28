"""Single source of truth for the app version.

Bump this in the same commit as the release tag: the updater compares it
against the latest GitHub release tag to decide whether an update exists.
"""
from __future__ import annotations

__version__ = "1.0.1"

GITHUB_REPO = "liamgelfand/application-tracker"


def version_tuple(raw: str) -> tuple[int, ...]:
    """Parse "v1.2.3" / "1.2.3-beta" into (1, 2, 3) for ordering.

    Anything unparseable becomes (0,), which sorts below every real release so
    a malformed tag can never look newer than what is installed.
    """
    cleaned = raw.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return version_tuple(candidate) > version_tuple(current)
