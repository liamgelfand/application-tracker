from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Application,
    ApplicationStatus,
    EventSource,
    StatusEvent,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)
from .email.prefilter import is_otp_or_verification

# Prefer explicit numeric "12345 - Role" (IBM-style) before looser labels.
_JOB_ID_PATTERNS = [
    re.compile(r"\b(\d{5,8})\s*[-–—]\s+[A-Za-z]"),
    re.compile(
        r"\b(?:requisition|job\s*id|job\s*#|posting\s*id)\s*[:#-]?\s*([A-Z0-9-]{4,})\b",
        re.IGNORECASE,
    ),
]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation/common suffixes for fuzzy comparison."""
    text = text.lower()
    text = re.sub(
        r"\b(inc|llc|ltd|corp|co|group|technologies|tech|solutions|"
        r"recruiting|careers|jobs|notifications?|workday|notify|"
        r"assessment|team|human resources)\b",
        "",
        text,
    )
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_placeholder_title(title: str | None) -> bool:
    if not title:
        return True
    return _normalize(title) in {"", "unknown", "n a", "na", "none", "null"}


def extract_job_id(*texts: str | None) -> str | None:
    """Pull an employer job/req id out of subject/body when present."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    for pat in _JOB_ID_PATTERNS:
        m = pat.search(blob)
        if m:
            return m.group(1).strip()
    return None


def _titles_match(a: str | None, b: str | None) -> bool:
    """True when two role titles refer to the same posting (strict)."""
    if _is_placeholder_title(a) or _is_placeholder_title(b):
        return False
    na, nb = _normalize(a or ""), _normalize(b or "")
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Substring only when the shorter title is long enough to be specific
    # (avoids "software developer" matching every SWE-ish IBM role).
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) < 28:
        return False
    return short in long


def _same_role(
    app: Application,
    *,
    title: str | None,
    job_id: str | None,
) -> bool:
    if job_id and app.job_id and job_id.strip() == app.job_id.strip():
        return True
    if job_id and app.job_id and job_id.strip() != app.job_id.strip():
        return False
    return _titles_match(app.title, title)


def _find_existing_application(
    db: Session,
    company: str | None,
    title: str | None,
    job_id: str | None = None,
) -> Application | None:
    """Match by job_id first, then company+title. Never collapse different roles."""
    if not company:
        return None
    norm_company = _normalize(company)
    if not norm_company:
        return None

    apps = list(db.execute(select(Application)).scalars().all())
    company_matches = [a for a in apps if _normalize(a.company) == norm_company]
    if not company_matches:
        company_matches = [
            a
            for a in apps
            if norm_company in _normalize(a.company)
            or _normalize(a.company) in norm_company
        ]
    if not company_matches:
        return None

    if job_id:
        jid = job_id.strip()
        for app in company_matches:
            if app.job_id and app.job_id.strip() == jid:
                return app
        # Known job_id that doesn't match any row → new role at this company.
        if title and not _is_placeholder_title(title):
            for app in company_matches:
                if _titles_match(app.title, title):
                    return app
        return None

    if title and not _is_placeholder_title(title):
        for app in company_matches:
            if _titles_match(app.title, title):
                return app
        # Distinct role at same company → do not merge.
        return None

    # No title and no job_id: refuse to guess among multiple company rows.
    if len(company_matches) == 1 and _is_placeholder_title(company_matches[0].title):
        return company_matches[0]
    return None


def _company_from_sender(sender: str | None) -> str | None:
    """Extract a human-readable company name from an email From header."""
    if not sender:
        return None
    m = re.match(r"^(.+?)\s*<", sender)
    if m:
        name = m.group(1).strip().strip('"')
        name = re.sub(
            r"\b(assessment|recruiting|careers|talent|hr|human resources|"
            r"notifications?|no-?reply|team)\b",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip(" -|,")
        if name:
            return name
    if "@" in sender:
        domain = sender.split("@")[1].split(".")[0]
        if domain.lower() not in {"email", "mail", "noreply", "no-reply"}:
            return domain.capitalize()
    return sender.strip() or None


def _coerce_status(value: str | None) -> ApplicationStatus | None:
    if not value:
        return None
    try:
        return ApplicationStatus(value)
    except ValueError:
        return None


def _enrich_application(
    app: Application,
    *,
    company: str | None,
    title: str | None,
    job_id: str | None = None,
) -> None:
    """Fill missing/placeholder fields on an existing application."""
    if title and not _is_placeholder_title(title) and _is_placeholder_title(app.title):
        app.title = title
    if job_id and not app.job_id:
        app.job_id = job_id.strip()


def _create_or_merge(
    db: Session,
    *,
    company: str | None,
    title: str | None,
    status: ApplicationStatus | None,
    summary: str | None,
    source: EventSource,
    job_id: str | None = None,
) -> Application | None:
    """Merge into a matching role or create a new application."""
    company = (company or "").strip() or None
    title = (title or "").strip() or None
    job_id = (job_id or "").strip() or None
    if _is_placeholder_title(title):
        title = None

    if not company:
        return None

    existing = _find_existing_application(db, company, title, job_id)
    if existing is not None:
        _enrich_application(existing, company=company, title=title, job_id=job_id)
        if status and status != existing.status:
            old = existing.status
            existing.status = status
            db.add(
                StatusEvent(
                    application_id=existing.id,
                    from_status=old,
                    to_status=existing.status,
                    note=summary or "Updated from email",
                    source=source,
                )
            )
        elif title or job_id:
            db.add(
                StatusEvent(
                    application_id=existing.id,
                    from_status=existing.status,
                    to_status=existing.status,
                    note=summary or "Enriched from email",
                    source=source,
                )
            )
        return existing

    app = Application(
        company=company,
        title=title or "Unknown",
        job_id=job_id,
        status=status or ApplicationStatus.applied,
        source="email",
        date_applied=datetime.now(timezone.utc),
    )
    db.add(app)
    db.flush()
    db.add(
        StatusEvent(
            application_id=app.id,
            from_status=None,
            to_status=app.status,
            note=summary or "Created from email",
            source=source,
        )
    )
    return app


def build_suggestion_from_analysis(
    analysis: dict,
    *,
    sender: str,
    subject: str,
    snippet: str,
) -> Suggestion | None:
    """Turn an analyzer result into a pending Suggestion (or None if not relevant)."""
    if not analysis.get("is_job_related"):
        return None

    if is_otp_or_verification(subject, snippet):
        return None

    kind_raw = analysis.get("kind")
    try:
        kind = SuggestionKind(kind_raw) if kind_raw else SuggestionKind.note
    except ValueError:
        kind = SuggestionKind.note

    suggested_status = _coerce_status(analysis.get("suggested_status"))
    company = analysis.get("company") or _company_from_sender(sender)
    title = analysis.get("title")
    if _is_placeholder_title(title):
        title = None

    job_id = analysis.get("job_id") or extract_job_id(subject, snippet)
    if isinstance(job_id, str):
        job_id = job_id.strip() or None
    else:
        job_id = None

    if kind == SuggestionKind.new_application and not company:
        return None

    # If LLM attached a status_change to a company match but we have a distinct
    # role/job_id, force a new_application so we don't pollute the wrong row.
    app_id = analysis.get("application_id")
    if (
        kind == SuggestionKind.status_change
        and app_id is not None
        and (title or job_id)
    ):
        # Retargeting happens at apply-time; keep payload accurate here.
        pass

    # Distinct role signals without a matching id → treat as new application.
    if kind == SuggestionKind.status_change and (title or job_id) and not app_id:
        kind = SuggestionKind.new_application

    payload = {
        "company": company,
        "title": title,
        "job_id": job_id,
    }

    return Suggestion(
        application_id=app_id if isinstance(app_id, int) else None,
        kind=kind,
        status=SuggestionStatus.pending,
        suggested_status=suggested_status,
        summary=analysis.get("summary"),
        payload=json.dumps(payload),
        confidence=analysis.get("confidence"),
        email_subject=subject,
        email_sender=sender,
        email_snippet=snippet[:500],
    )


def apply_suggestion(
    db: Session,
    suggestion: Suggestion,
    *,
    source: EventSource = EventSource.email,
    company_override: str | None = None,
    title_override: str | None = None,
    status_override: ApplicationStatus | None = None,
) -> Application | None:
    """Apply a suggestion's change. Returns the affected application (if any)."""
    if is_otp_or_verification(
        suggestion.email_subject or "", suggestion.email_snippet or ""
    ):
        suggestion.status = SuggestionStatus.rejected
        db.commit()
        return None

    payload = json.loads(suggestion.payload) if suggestion.payload else {}
    if company_override is not None:
        payload["company"] = company_override
    if title_override is not None:
        payload["title"] = title_override
    suggestion.payload = json.dumps(payload)
    if status_override is not None:
        suggestion.suggested_status = status_override

    company = payload.get("company") or _company_from_sender(suggestion.email_sender)
    title = payload.get("title")
    if _is_placeholder_title(title):
        title = None
    job_id = payload.get("job_id") or extract_job_id(
        suggestion.email_subject, suggestion.email_snippet
    )

    app: Application | None = None

    if suggestion.kind == SuggestionKind.new_application:
        app = _create_or_merge(
            db,
            company=company,
            title=title,
            job_id=job_id,
            status=suggestion.suggested_status,
            summary=suggestion.summary,
            source=source,
        )
    elif suggestion.application_id:
        app = db.get(Application, suggestion.application_id)
        if app is not None:
            # Retarget when the LLM pointed at the wrong role at the same company.
            if (title or job_id) and not _same_role(app, title=title, job_id=job_id):
                better = _find_existing_application(db, company, title, job_id)
                if better is not None:
                    app = better
                else:
                    app = _create_or_merge(
                        db,
                        company=company,
                        title=title,
                        job_id=job_id,
                        status=suggestion.suggested_status or ApplicationStatus.applied,
                        summary=suggestion.summary,
                        source=source,
                    )
                    suggestion.status = SuggestionStatus.approved
                    db.commit()
                    return app

            _enrich_application(app, company=company, title=title, job_id=job_id)
            if company and _normalize(company) not in _normalize(app.company):
                better = _find_existing_application(db, company, title, job_id)
                if better is not None:
                    app = better
                    _enrich_application(app, company=company, title=title, job_id=job_id)
            if (
                suggestion.kind == SuggestionKind.status_change
                and suggestion.suggested_status
                and suggestion.suggested_status != app.status
            ):
                old = app.status
                app.status = suggestion.suggested_status
                db.add(
                    StatusEvent(
                        application_id=app.id,
                        from_status=old,
                        to_status=app.status,
                        note=suggestion.summary or "Updated from email",
                        source=source,
                    )
                )
            else:
                db.add(
                    StatusEvent(
                        application_id=app.id,
                        from_status=app.status,
                        to_status=app.status,
                        note=suggestion.summary or "Email note",
                        source=source,
                    )
                )
        else:
            app = _create_or_merge(
                db,
                company=company,
                title=title,
                job_id=job_id,
                status=suggestion.suggested_status,
                summary=suggestion.summary,
                source=source,
            )
    else:
        app = _create_or_merge(
            db,
            company=company,
            title=title,
            job_id=job_id,
            status=suggestion.suggested_status or ApplicationStatus.applied,
            summary=suggestion.summary,
            source=source,
        )

    suggestion.status = SuggestionStatus.approved
    db.commit()
    return app
