"""Infer application status from email subject/summary when the LLM is vague."""
from __future__ import annotations

import re

from ..models import ApplicationStatus

_REJECT_HINTS = (
    "reject",
    "not moving forward",
    "will not be moving",
    "won't be moving",
    "decided not to",
    "not selected",
    "unfortunately",
    "other candidates",
)

_OA_RE = re.compile(
    r"\b(?:codesignal|coderbyte|hackerrank|hirevue|karat|codility|pymetrics)\b"
    r"|coding assessment"
    r"|online assessment"
    r"|technical assessment"
    r"|skills assessment"
    r"|complete (?:your |an |the )?assessment"
    r"|complete your digital screen"
    r"|digital screen"
    r"|invited (?:you )?to complete .{0,60}(?:assessment|assignment|codesignal|coderbyte)"
    r"|assessment (?:invite|invitation|via)"
    r"|assessments? invitation"
    r"|you are invited to complete an assessment"
    r"|virtual job try-?out"
    r"|on-demand video interview"
    r"|one-way (?:video )?interview"
    r"|take-?home"
    r"|coding challenge"
    r"|coding test"
    r"|assessment is being reviewed"
    r"|result of your assessment",
    re.IGNORECASE,
)

# Live conversation — not a recorded/on-demand screen.
_LIVE_INTERVIEW_RE = re.compile(
    r"technical interview invitation"
    r"|interview (?:invitation|invite|scheduled|submission)"
    r"|(?:schedule|scheduled) (?:an |your )?interview"
    r"|onsite(?: interview)?"
    r"|on-site(?: interview)?"
    r"|final round"
    r"|super\s*day"
    r"|phone interview"
    r"|video interview(?! assessment)",
    re.IGNORECASE,
)

_ON_DEMAND_RE = re.compile(
    r"on-demand|one-way|hirevue|recorded (?:video )?interview",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(
    r"phone screen"
    r"|recruiter (?:screen|call)"
    r"|intro(?:ductory)? call"
    r"|schedule a (?:phone )?call"
    r"|hop on a call",
    re.IGNORECASE,
)

_OFFER_RE = re.compile(
    r"\b(?:offer letter|job offer|we(?:'re| are) (?:pleased|excited) to offer)\b",
    re.IGNORECASE,
)


def looks_like_rejection(*parts: str | None) -> bool:
    blob = _blob(*parts)
    return any(h in blob for h in _REJECT_HINTS)


def looks_like_online_assessment(*parts: str | None) -> bool:
    return bool(_OA_RE.search(_blob(*parts)))


def looks_like_phone_screen(*parts: str | None) -> bool:
    return bool(_PHONE_RE.search(_blob(*parts)))


def looks_like_live_interview(*parts: str | None) -> bool:
    blob = _blob(*parts)
    if _ON_DEMAND_RE.search(blob):
        return False
    return bool(_LIVE_INTERVIEW_RE.search(blob))


def infer_status_from_text(*parts: str | None) -> ApplicationStatus | None:
    """Best-effort status from subject/summary/snippet. Rejection wins."""
    blob = _blob(*parts)
    if not blob.strip():
        return None
    if looks_like_rejection(blob):
        return ApplicationStatus.rejected
    if _OFFER_RE.search(blob):
        return ApplicationStatus.offer
    if looks_like_live_interview(blob):
        return ApplicationStatus.interview
    if looks_like_online_assessment(blob):
        return ApplicationStatus.online_assessment
    if _PHONE_RE.search(blob):
        return ApplicationStatus.phone_screen
    return None


def refine_suggested_status(
    given: ApplicationStatus | None,
    *parts: str | None,
) -> ApplicationStatus | None:
    """Prefer a concrete inferred stage over a missing or mis-tagged one."""
    inferred = infer_status_from_text(*parts)
    if given in {
        ApplicationStatus.rejected,
        ApplicationStatus.offer,
        ApplicationStatus.accepted,
        ApplicationStatus.ghosted,
    }:
        return given
    if inferred == ApplicationStatus.rejected:
        return inferred
    if inferred == ApplicationStatus.online_assessment and given in {
        None,
        ApplicationStatus.applied,
        ApplicationStatus.phone_screen,
        ApplicationStatus.interview,
    }:
        # Keep a real interview invite even if the email also mentions an OA.
        if given == ApplicationStatus.interview and looks_like_live_interview(*parts):
            return given
        return inferred
    if given is None:
        return inferred
    return given


def _blob(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)
