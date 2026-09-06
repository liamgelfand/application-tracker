from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Application, ApplicationStatus
from ..llm.service import complete_json, get_active_provider
from ..suggestion_service import _titles_match, extract_job_id
from .prefilter import clean_body, is_blocked, is_otp_or_verification
from .subject_fastpath import try_fastpath

logger = logging.getLogger("tracker.analyzer")

SYSTEM_PROMPT = (
    "You are a precise assistant that classifies emails for a job-application tracker. "
    "Your only job is to decide whether an email is related to a specific job application "
    "(not generic career newsletters or unrelated marketing) and, if so, what action to take.\n\n"
    "IMPORTANT RULES you must always follow:\n"
    "1. Identify the hiring company AND the specific role. A single company (e.g. IBM) often "
    "has MANY separate applications. Never treat 'same company' as the same application.\n"
    "2. Extract job_id when the email includes a requisition/job/posting number "
    "(e.g. '128506' in 'Liam Gelfand - 128506 - Software Developer…'). Put it in job_id.\n"
    "3. Match to an existing application ONLY when job_id matches, OR the role title clearly "
    "matches that row's title. If the company exists but the role/job_id is different or new → "
    "kind='new_application' with application_id=null.\n"
    "4. Only use an application_id that appears in the provided list — never invent one. "
    "If unsure which of several same-company rows it is, prefer new_application over guessing.\n"
    "5. Marketing emails, order confirmations, food delivery, banking alerts, payroll, "
    "and social media notifications are NEVER job-related even if they contain the word 'application'.\n"
    "6. Security codes, OTP, 'verify your email', and 'enter this code to continue' emails "
    "are NOT useful for tracking. Set is_job_related=false for those.\n"
    "7. Always extract the job title when mentioned. Vague follow-ups with no role and no job_id "
    "should use kind='note' with application_id=null — do not attach them to a random same-company row."
)

VALID_STATUSES = [s.value for s in ApplicationStatus]

USER_TEMPLATE = """User's existing applications (id | company | title | job_id | current status):
{applications}

Email to analyze:
From: {sender}
Subject: {subject}
Body:
\"\"\"
{body}
\"\"\"

Think step by step (internally), then respond with ONLY a JSON object:
{{
  "company": string|null,          // hiring company name — always fill this if job-related
  "title": string|null,            // specific role / program name from the email
  "job_id": string|null,           // requisition/job/posting number if present
  "is_job_related": boolean,
  "kind": "status_change" | "new_application" | "note" | null,
  "application_id": number|null,   // ONLY an id from the list above when role/job_id matches, else null
  "suggested_status": {statuses}|null,
  "summary": string,               // one sentence describing the suggested action
  "confidence": number             // 0-100
}}

Status guidance (pipeline order: applied → online_assessment → phone_screen → interview → offer):
- Application confirmation / receipt → kind=new_application, suggested_status="applied"
- Coding test / HireVue / CodeSignal / Coderbyte / HackerRank / take-home / "complete your assessment" / digital screen / on-demand video interview → suggested_status="online_assessment" (NOT phone_screen)
- Recruiter call / live phone screen → suggested_status="phone_screen"
- Live interview invite or scheduling (not a recorded/on-demand screen) → suggested_status="interview"
- Offer letter → suggested_status="offer"
- Rejection / not moving forward / other candidates → kind=status_change, suggested_status="rejected"
- Cold recruiter outreach (not yet applied) → kind=new_application, suggested_status="saved"

CRITICAL: If the email is a rejection (or any clear status update), you MUST set
suggested_status to the matching status value. Never leave suggested_status null
when kind is status_change — a null status only adds a note and does not update the board.
"""


def analyze_email(
    db: Session,
    *,
    sender: str,
    subject: str,
    body: str,
) -> dict | None:
    """Analyze one email. Returns None if classification must wait for an LLM."""
    if is_blocked(sender):
        logger.info("Skipped (blocklisted sender): %r", sender)
        return {
            "is_job_related": False,
            "kind": None,
            "application_id": None,
            "suggested_status": None,
            "company": None,
            "title": None,
            "job_id": None,
            "summary": "Skipped blocklisted sender.",
            "confidence": 100,
        }

    if is_otp_or_verification(subject, body):
        logger.info("Skipped (OTP/verification email): subject=%r", subject)
        return {
            "is_job_related": False,
            "kind": None,
            "application_id": None,
            "suggested_status": None,
            "company": None,
            "title": None,
            "job_id": None,
            "summary": "Skipped verification/OTP email — no application data.",
            "confidence": 100,
        }

    fast = try_fastpath(subject, body, sender)
    if fast:
        job_id = extract_job_id(subject, body)
        if job_id:
            fast["job_id"] = job_id
        apps_quick = list(db.execute(select(Application)).scalars().all())
        company = (fast.get("company") or "").lower()
        title = fast.get("title")
        matched = None
        for a in apps_quick:
            if not company or company not in (a.company or "").lower():
                continue
            if job_id and a.job_id and job_id == a.job_id:
                matched = a
                break
            if title and _titles_match(a.title, title):
                matched = a
                break
        if matched is not None:
            fast["kind"] = "status_change"
            fast["application_id"] = matched.id
        else:
            # New role at a known (or unknown) company — do not attach to a sibling.
            fast["kind"] = "new_application"
            fast["application_id"] = None
        logger.info(
            "Fastpath hit: subject=%r company=%r title=%r job_id=%r app_id=%r",
            subject,
            fast.get("company"),
            fast.get("title"),
            fast.get("job_id"),
            fast.get("application_id"),
        )
        return fast

    apps = db.execute(select(Application)).scalars().all()
    app_lines = (
        "\n".join(
            f"{a.id} | {a.company} | {a.title} | {a.job_id or '-'} | {a.status.value}"
            for a in apps
        )
        if apps
        else "(none yet)"
    )

    cleaned_body = clean_body(body)

    if get_active_provider(db) is None:
        logger.info("No LLM provider; skipping non-fastpath email: %r", subject)
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                applications=app_lines,
                sender=sender,
                subject=subject,
                body=cleaned_body,
                statuses=json.dumps(VALID_STATUSES),
            ),
        },
    ]
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    result = complete_json(db, messages)
    # Prefer regex job_id from subject when the model omits it.
    if not result.get("job_id"):
        jid = extract_job_id(subject, body)
        if jid:
            result["job_id"] = jid
    return result
