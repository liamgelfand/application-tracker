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


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation/common suffixes for fuzzy comparison."""
    text = text.lower()
    text = re.sub(r"\b(inc|llc|ltd|corp|co|group|technologies|tech|solutions|recruiting|careers|jobs|notifications?|workday|notify)\b", "", text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return text.strip()


def _find_existing_application(db: Session, company: str | None, title: str | None) -> Application | None:
    """Return an existing application that fuzzy-matches company + (optionally) title."""
    if not company:
        return None
    norm_company = _normalize(company)
    if not norm_company:
        return None
    apps = db.execute(select(Application)).scalars().all()
    for app in apps:
        if _normalize(app.company) == norm_company:
            if title is None or _normalize(title) in _normalize(app.title or "") or _normalize(app.title or "") in _normalize(title):
                return app
            # Company match alone is a strong signal
            return app
    return None


def _company_from_sender(sender: str | None) -> str | None:
    """Extract a human-readable company name from an email From header."""
    if not sender:
        return None
    # "Appian Recruiting <careers@appian.com>" → "Appian Recruiting"
    m = re.match(r"^(.+?)\s*<", sender)
    if m:
        return m.group(1).strip()
    # "careers@appian.com" → "appian"
    if "@" in sender:
        return sender.split("@")[1].split(".")[0].capitalize()
    return sender.strip() or None


def _coerce_status(value: str | None) -> ApplicationStatus | None:
    if not value:
        return None
    try:
        return ApplicationStatus(value)
    except ValueError:
        return None


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

    kind_raw = analysis.get("kind")
    try:
        kind = SuggestionKind(kind_raw) if kind_raw else SuggestionKind.note
    except ValueError:
        kind = SuggestionKind.note

    suggested_status = _coerce_status(analysis.get("suggested_status"))
    payload = {
        "company": analysis.get("company"),   # now always populated for job-related emails
        "title": analysis.get("title"),
    }

    return Suggestion(
        application_id=analysis.get("application_id"),
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
    db: Session, suggestion: Suggestion, *, source: EventSource = EventSource.email
) -> Application | None:
    """Apply a suggestion's change. Returns the affected application (if any)."""
    app: Application | None = None

    if suggestion.kind == SuggestionKind.new_application:
        payload = json.loads(suggestion.payload) if suggestion.payload else {}
        company = payload.get("company") or _company_from_sender(suggestion.email_sender)
        title = payload.get("title")

        # Fuzzy dedup: if we already have this company, update instead of creating.
        existing = _find_existing_application(db, company, title)
        if existing is not None:
            if (
                suggestion.suggested_status
                and suggestion.suggested_status != existing.status
            ):
                old = existing.status
                existing.status = suggestion.suggested_status
                db.add(
                    StatusEvent(
                        application_id=existing.id,
                        from_status=old,
                        to_status=existing.status,
                        note=suggestion.summary or "Updated from email",
                        source=source,
                    )
                )
            app = existing
        else:
            app = Application(
                company=company or "Unknown",
                title=title or "Unknown",
                status=suggestion.suggested_status or ApplicationStatus.applied,
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
                    note=suggestion.summary or "Created from email",
                    source=source,
                )
            )
    elif suggestion.application_id:
        app = db.get(Application, suggestion.application_id)
        if app is not None:
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
            # application_id pointed to a non-existent row — create a new entry.
            payload = json.loads(suggestion.payload) if suggestion.payload else {}
            company = payload.get("company") or _company_from_sender(suggestion.email_sender)
            title = payload.get("title")
            app = Application(
                company=company or "Unknown",
                title=title or "Unknown",
                status=suggestion.suggested_status or ApplicationStatus.applied,
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
                    note=suggestion.summary or "Created from email",
                    source=source,
                )
            )
    else:
        # No application_id — LLM used status_change for an unknown company.
        # Always create a new entry, using sender name as company fallback.
        payload = json.loads(suggestion.payload) if suggestion.payload else {}
        company = payload.get("company") or _company_from_sender(suggestion.email_sender)
        title = payload.get("title")
        app = Application(
            company=company or "Unknown",
            title=title or "Unknown",
            status=suggestion.suggested_status or ApplicationStatus.applied,
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
                note=suggestion.summary or "Created from email",
                source=source,
            )
        )

    suggestion.status = SuggestionStatus.approved
    db.commit()
    return app
