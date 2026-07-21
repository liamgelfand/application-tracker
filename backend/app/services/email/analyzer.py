from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Application, ApplicationStatus
from ..llm.service import complete_json

SYSTEM_PROMPT = (
    "You are an assistant that helps track job applications by analyzing a single "
    "email. Decide whether the email relates to a job application. Job-related emails "
    "include: application confirmations, recruiter outreach, interview invitations or "
    "scheduling, take-home assessments, offers, rejections, and any follow-up from a "
    "hiring team. When in doubt, flag it as job-related — it is far better to surface "
    "a borderline email for review than to silently miss a real one. "
    "If it does relate to a job application, try to match it to one of the user's "
    "existing applications by company and role, and suggest an updated status."
)

VALID_STATUSES = [s.value for s in ApplicationStatus]

USER_TEMPLATE = """The user's existing applications (id | company | title | current status):
{applications}

Email:
From: {sender}
Subject: {subject}
Body:
\"\"\"
{body}
\"\"\"

Respond with ONLY a JSON object using exactly these keys:
{{
  "is_job_related": boolean,
  "kind": "status_change" | "new_application" | "note" | null,
  "application_id": number|null,   // id of the matching existing application, or null
  "suggested_status": {statuses}|null,
  "company": string|null,          // for new_application
  "title": string|null,            // for new_application
  "summary": string,               // 1 sentence explaining the suggested action
  "confidence": number             // 0-100
}}

Guidance:
- If it matches an existing application and implies a status change, use kind="status_change" with application_id and suggested_status.
- If it is a job application confirmation for a role NOT in the list, use kind="new_application" with company/title and suggested_status="applied".
- If job-related but no clear action, use kind="note".
- If not job-related, set is_job_related=false and kind=null.
"""


def analyze_email(
    db: Session,
    *,
    sender: str,
    subject: str,
    body: str,
) -> dict:
    apps = db.execute(select(Application)).scalars().all()
    if apps:
        app_lines = "\n".join(
            f"{a.id} | {a.company} | {a.title} | {a.status.value}" for a in apps
        )
    else:
        app_lines = "(none yet)"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                applications=app_lines,
                sender=sender,
                subject=subject,
                body=body.strip()[:6000],
                statuses=json.dumps(VALID_STATUSES),
            ),
        },
    ]
    result = complete_json(db, messages)
    return result
