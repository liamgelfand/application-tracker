from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Application, ApplicationStatus
from ..llm.service import complete_json
from .prefilter import clean_body, is_blocked, is_otp_or_verification

logger = logging.getLogger("tracker.analyzer")

SYSTEM_PROMPT = (
    "You are a precise assistant that classifies emails for a job-application tracker. "
    "Your only job is to decide whether an email is related to a specific job application "
    "(not generic career newsletters or unrelated marketing) and, if so, what action to take.\n\n"
    "IMPORTANT RULES you must always follow:\n"
    "1. First, identify the hiring company from the email (sender domain, body, or subject). "
    "Write this company name in the 'company' field EVERY TIME the email is job-related, "
    "regardless of whether it's a new or existing application.\n"
    "2. Check if that company is already in the user's application list.\n"
    "   - If YES → use kind='status_change' with the exact application_id from the list.\n"
    "   - If NO → use kind='new_application'. NEVER use kind='status_change' for a company "
    "not in the list.\n"
    "3. Only use an application_id that appears in the provided list — never invent one.\n"
    "4. Marketing emails, order confirmations, food delivery, banking alerts, payroll, "
    "and social media notifications are NEVER job-related even if they contain the word 'application'.\n"
    "5. Security codes, OTP, 'verify your email', and 'enter this code to continue' emails "
    "are NOT useful for tracking. Set is_job_related=false for those — never create a new "
    "application from them.\n"
    "6. Always extract the job title when the email mentions a specific role. If the email "
    "is only a vague follow-up (assessment invite with no role name) and the company is "
    "already in the list, use status_change on that application — do not invent a title."
)

VALID_STATUSES = [s.value for s in ApplicationStatus]

USER_TEMPLATE = """User's existing applications (id | company | title | current status):
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
  "is_job_related": boolean,
  "kind": "status_change" | "new_application" | "note" | null,
  "application_id": number|null,   // ONLY use an id from the list above, or null
  "suggested_status": {statuses}|null,
  "title": string|null,            // job title — for new_application
  "summary": string,               // one sentence describing the suggested action
  "confidence": number             // 0-100
}}

Status guidance for new_application:
- Application confirmation / receipt → "applied"
- Interview invite or scheduling → "interview"
- Phone screen / recruiter call → "phone_screen"
- Offer letter → "offer"
- Rejection → "rejected"
- Cold recruiter outreach (not yet applied) → "saved"
"""


def analyze_email(
    db: Session,
    *,
    sender: str,
    subject: str,
    body: str,
) -> dict | None:
    """Analyze one email. Returns None if the sender is on the blocklist."""
    if is_blocked(sender):
        logger.info("Skipped (blocklisted sender): %r", sender)
        return None

    if is_otp_or_verification(subject, body):
        logger.info("Skipped (OTP/verification email): subject=%r", subject)
        return {
            "is_job_related": False,
            "kind": None,
            "application_id": None,
            "suggested_status": None,
            "company": None,
            "title": None,
            "summary": "Skipped verification/OTP email — no application data.",
            "confidence": 100,
        }

    apps = db.execute(select(Application)).scalars().all()
    app_lines = (
        "\n".join(f"{a.id} | {a.company} | {a.title} | {a.status.value}" for a in apps)
        if apps
        else "(none yet)"
    )

    cleaned_body = clean_body(body)

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
    return complete_json(db, messages)
