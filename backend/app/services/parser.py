from __future__ import annotations

from sqlalchemy.orm import Session

from ..schemas import ParsedJob
from .llm.service import complete_json

SYSTEM_PROMPT = (
    "You are a precise information extraction assistant. You are given the raw text "
    "of a job listing (possibly messy, copied from a website or email). Extract the "
    "structured fields. Only use information present in the text; if a field is not "
    "present, use null (or an empty list for skills). Do not invent values."
)

USER_TEMPLATE = """Extract the following fields from the job listing below and respond
with ONLY a JSON object using exactly these keys:

{{
  "company": string|null,
  "title": string|null,
  "location": string|null,
  "url": string|null,
  "salary": string|null,
  "source": string|null,        // e.g. LinkedIn, Indeed, company site, if identifiable
  "description": string|null,   // a concise 1-3 sentence summary of the role
  "skills": string[]            // key skills / technologies mentioned
}}

Job listing text:
\"\"\"
{text}
\"\"\"
"""


def parse_job_listing(db: Session, text: str) -> ParsedJob:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(text=text.strip()[:12000])},
    ]
    data = complete_json(db, messages)

    skills = data.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    return ParsedJob(
        company=data.get("company"),
        title=data.get("title"),
        location=data.get("location"),
        url=data.get("url"),
        salary=data.get("salary"),
        source=data.get("source"),
        description=data.get("description"),
        skills=[str(s) for s in skills][:25],
    )
