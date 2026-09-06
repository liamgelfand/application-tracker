"""Regex fast-path for common application confirmation subjects.

Avoids an LLM round-trip when the subject already encodes company + role.
"""
from __future__ import annotations

import re

from ...models import ApplicationStatus
from ..status_inference import looks_like_online_assessment, looks_like_rejection

# "Leidos -Thank You For Applying to Entry-Level Computer Scientist"
# "Acme | Thank you for applying to Software Engineer"
_PREFIX_COMPANY = re.compile(
    r"^(?P<company>[^|\-–—]+?)\s*[-–—|]\s*.*?"
    r"thank you for (?:your )?apply(?:ing)?"
    r"(?:\s+to\s+(?P<title>.+))?$",
    re.IGNORECASE,
)

# "Thank you for applying to Notion!" / "Thank you for your application to Acme"
_THANK_YOU = re.compile(
    r"thank you for (?:your )?(?:application|apply(?:ing)?)"
    r"(?:\s+to\s+(?P<company_or_title>.+))?$",
    re.IGNORECASE,
)

_ROLE_IN_BODY = re.compile(
    r"(?:application for (?:the )?(?P<title>.+?)(?:\s+role|\s+position)|"
    r"for the (?P<title2>.+?)(?:\s+role|\s+position))",
    re.IGNORECASE,
)
_BRACKET_ROLE = re.compile(r"\[(?:\d{4})\]\s*(?P<title>[^\n\r]+)", re.IGNORECASE)
_OA_WITH = re.compile(
    r"assessment with (?P<company>[^-\n|,]+?)(?:\s*[-–—|]|$)", re.IGNORECASE
)
_OA_IBM = re.compile(
    r"action required:\s*(?P<company>\S+)\s+coding assessment", re.IGNORECASE
)
_OA_HACKERRANK_FOR = re.compile(
    r"hackerrank for (?P<company>.+?)(?:\s*<|$)", re.IGNORECASE
)
_OA_INVITED = re.compile(
    r"^(?P<company>.+?) invited you to complete", re.IGNORECASE
)
_OA_CAREERS = re.compile(r"^(?P<company>.+?) careers\b", re.IGNORECASE)
_OA_YOUR = re.compile(r"your (?P<company>.+?) assessments?", re.IGNORECASE)
_OA_REVIEWED_BY = re.compile(r"reviewed by (?P<company>.+)$", re.IGNORECASE)
_OA_AT = re.compile(r"\bat (?P<company>.+)$", re.IGNORECASE)
_OA_JOB_TITLE = re.compile(
    r"\b\d{5,8}\s*[-–—]\s+(?P<title>.+)$", re.IGNORECASE
)

# Tokens that are role adjectives, not company names.
_BAD_COMPANY = {
    "entry",
    "entry level",
    "entrylevel",
    "level",
    "software",
    "engineer",
    "engineering",
    "intern",
    "internship",
    "new",
    "grad",
    "graduate",
    "junior",
    "senior",
    "the",
    "our",
    "your",
    "a",
    "an",
    "job",
    "position",
    "role",
    "application",
    "career",
    "careers",
}


def _clean_company(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip(" !|-–—,\"'")
    # Truncate trailing role-y tails sometimes glued on
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return None
    key = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    if key in _BAD_COMPANY or len(key) < 2:
        return None
    # "Entry-Level Computer Scientist" is a title, not a company
    if key.startswith("entry level") or key.startswith("entrylevel"):
        return None
    return name


def _title_from_body(body: str) -> str | None:
    bm = _ROLE_IN_BODY.search(body or "")
    if bm:
        return (bm.group("title") or bm.group("title2") or "").strip(" .")
    br = _BRACKET_ROLE.search(body or "")
    if br:
        return br.group("title").strip(" .")
    return None


def _company_from_sender(sender: str) -> str | None:
    sm = re.match(r"^(.+?)\s*<", sender or "")
    if not sm:
        return None
    raw = sm.group(1)
    raw = re.sub(
        r"\b(recruiting|careers|assessment|team|no-?reply|donotreply|"
        r"do.?not.?reply|hr|workday|talent)\b",
        "",
        raw,
        flags=re.IGNORECASE,
    )
    # "donotreply_Leidos_HR workday" → keep Leidos-ish tokens
    raw = raw.replace("_", " ")
    return _clean_company(raw)


def _company_from_oa(subject: str, sender: str) -> str | None:
    for pat in (
        _OA_IBM,
        _OA_WITH,
        _OA_INVITED,
        _OA_CAREERS,
        _OA_YOUR,
        _OA_REVIEWED_BY,
        _OA_AT,
        _OA_HACKERRANK_FOR,
    ):
        m = pat.search(subject or "") or pat.search(sender or "")
        if m:
            company = _clean_company(m.group("company"))
            if company:
                return company
    return _company_from_sender(sender)


def _try_assessment_fastpath(subject: str, body: str, sender: str) -> dict | None:
    if looks_like_rejection(subject, body, sender):
        return None
    if not looks_like_online_assessment(subject, body, sender):
        return None
    company = _company_from_oa(subject, sender)
    if not company:
        return None
    title = None
    tm = _OA_JOB_TITLE.search(subject or "")
    if tm:
        title = tm.group("title").strip(" !.-") or None
    if not title:
        title = _title_from_body(body)
    return {
        "company": company,
        "title": title,
        "is_job_related": True,
        "kind": "new_application",
        "application_id": None,
        "suggested_status": ApplicationStatus.online_assessment.value,
        "summary": f"Online assessment from {company}"
        + (f" for {title}" if title else "")
        + " (matched from subject line).",
        "confidence": 90 if title else 82,
        "fastpath": True,
    }


def try_fastpath(subject: str, body: str, sender: str) -> dict | None:
    """Return an analyzer-shaped dict if we can classify without the LLM."""
    subj = (subject or "").strip()
    if not subj:
        return None

    oa = _try_assessment_fastpath(subj, body, sender)
    if oa:
        return oa

    company: str | None = None
    title: str | None = None

    m = _PREFIX_COMPANY.search(subj)
    if m:
        company = _clean_company(m.group("company"))
        title = (m.group("title") or "").strip(" !.-") or None
    else:
        m2 = _THANK_YOU.search(subj)
        if not m2:
            return None
        # Everything after "applying to" may be a role ("Entry-Level …") or a company
        # ("Notion"). Prefer treating long/role-like strings as titles.
        rest = (m2.group("company_or_title") or "").strip(" !.-")
        rest_key = re.sub(r"[^a-z0-9 ]", "", rest.lower()).strip()
        if rest and (
            rest_key.startswith("entry level")
            or "engineer" in rest_key
            or "developer" in rest_key
            or "scientist" in rest_key
            or "intern" in rest_key
            or len(rest.split()) >= 4
        ):
            title = rest
            company = None
        else:
            company = _clean_company(rest)

    if not company:
        company = _company_from_sender(sender)
    if not company:
        # Can't safely invent a company — let the LLM handle it.
        return None

    if not title:
        title = _title_from_body(body)

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
