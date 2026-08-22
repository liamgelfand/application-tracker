"""Regex fast-path for common application confirmation subjects.

Avoids an LLM round-trip when the subject already encodes company + role.
"""
from __future__ import annotations

import re

from ...models import ApplicationStatus

# "Thank you for applying to Notion!" / "Thank you for your application to Acme"
_THANK_YOU = re.compile(
    r"thank you for (?:your )?apply(?:ing)?(?: to (?P<company>[^!|,.\-\n]+))?",
    re.IGNORECASE,
)
# "Thank you for applying to Roblox! ... Software Engineer, Early Career"
_ROLE_IN_BODY = re.compile(
    r"(?:application for (?:the )?(?P<title>.+?)(?:\s+role|\s+position)|"
    r"for the (?P<title2>.+?)(?:\s+role|\s+position))",
    re.IGNORECASE,
)
# "[2027] Software Engineer, Early Career"
_BRACKET_ROLE = re.compile(r"\[(?:\d{4})\]\s*(?P<title>[^\n\r]+)", re.IGNORECASE)


def try_fastpath(subject: str, body: str, sender: str) -> dict | None:
    """Return an analyzer-shaped dict if we can classify without the LLM."""
    subj = subject or ""
    m = _THANK_YOU.search(subj)
    if not m:
        return None

    company = (m.group("company") or "").strip(" !|-")
    if not company:
        # Fall back to display name before @
        sm = re.match(r"^(.+?)\s*<", sender or "")
        if sm:
            company = re.sub(
                r"\b(recruiting|careers|assessment|team|no-?reply)\b",
                "",
                sm.group(1),
                flags=re.IGNORECASE,
            ).strip(" -|,\"'")
    if not company:
        return None

    title = None
    bm = _ROLE_IN_BODY.search(body or "")
    if bm:
        title = (bm.group("title") or bm.group("title2") or "").strip(" .")
    if not title:
        br = _BRACKET_ROLE.search(body or "")
        if br:
            title = br.group("title").strip(" .")

    return {
        "company": company,
        "title": title,
        "is_job_related": True,
        "kind": "new_application",
        "application_id": None,
        "suggested_status": ApplicationStatus.applied.value,
        "summary": f"Application confirmation from {company}"
        + (f" for {title}" if title else "")
        + " (matched from subject line).",
        "confidence": 92 if title else 80,
        "fastpath": True,
    }
