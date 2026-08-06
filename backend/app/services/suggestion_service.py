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


def _find_existing_application(
    db: Session, company: str | None, title: str | None
) -> Application | None:
    """Return an existing application that fuzzy-matches company (+ optional title)."""
    if not company:
        return None
    norm_company = _normalize(company)
    if not norm_company:
        return None

    apps = list(db.execute(select(Application)).scalars().all())
    company_matches = [
        a for a in apps if _normalize(a.company) == norm_company
    ]
    if not company_matches:
        # Substring fallback: "Roblox Assessment" vs "Roblox"
        company_matches = [
            a
            for a in apps
            if norm_company in _normalize(a.company)
            or _normalize(a.company) in norm_company
        ]
    if not company_matches:
        return None

    if title and not _is_placeholder_title(title):
        norm_title = _normalize(title)
        for app in company_matches:
            at = _normalize(app.title or "")
            if not at or _is_placeholder_title(app.title):
                continue
            if norm_title in at or at in norm_title:
                return app

    # Prefer a non-placeholder title when merging into company-only matches.
    for app in company_matches:
        if not _is_placeholder_title(app.title):
            return app
    return company_matches[0]


def _company_from_sender(sender: str | None) -> str | None:
    """Extract a human-readable company name from an email From header."""
    if not sender:
        return None
    m = re.match(r"^(.+?)\s*<", sender)
    if m:
        name = m.group(1).strip().strip('"')
        # "Roblox Assessment" → "Roblox"
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
) -> None:
    """Fill missing/placeholder fields on an existing application."""
    if company and (_is_placeholder_title(app.company) or len(company) < len(app.company or "")):
        # Only replace company if ours looks cleaner and still matches.
        if _normalize(company) and _normalize(company) in _normalize(app.company or company):
            pass  # keep existing company name
    if title and not _is_placeholder_title(title) and _is_placeholder_title(app.title):
        app.title = title


def _create_or_merge(
    db: Session,
    *,
    company: str | None,
    title: str | None,
    status: ApplicationStatus | None,
    summary: str | None,
    source: EventSource,
) -> Application | None:
    """Merge into an existing company match or create a new application."""
    company = (company or "").strip() or None
    title = (title or "").strip() or None
    if _is_placeholder_title(title):
        title = None

    if not company:
        return None

    existing = _find_existing_application(db, company, title)
    if existing is not None:
        _enrich_application(existing, company=company, title=title)
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
        elif title and not _is_placeholder_title(title):
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

    # No existing match — require at least a company; title may be Unknown.
    app = Application(
        company=company,
        title=title or "Unknown",
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

    # Don't queue empty shells: new_application with no company is useless.
    if kind == SuggestionKind.new_application and not company:
        return None

    payload = {
        "company": company,
        "title": title,
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
    # Hard block: OTP / verification suggestions should never create rows.
    if is_otp_or_verification(
        suggestion.email_subject or "", suggestion.email_snippet or ""
    ):
        suggestion.status = SuggestionStatus.rejected
        db.commit()
        return None

    payload = json.loads(suggestion.payload) if suggestion.payload else {}
    company = payload.get("company") or _company_from_sender(suggestion.email_sender)
    title = payload.get("title")
    if _is_placeholder_title(title):
        title = None

    app: Application | None = None

    if suggestion.kind == SuggestionKind.new_application:
        app = _create_or_merge(
            db,
            company=company,
            title=title,
            status=suggestion.suggested_status,
            summary=suggestion.summary,
            source=source,
        )
    elif suggestion.application_id:
        app = db.get(Application, suggestion.application_id)
        if app is not None:
            _enrich_application(app, company=company, title=title)
            # If the LLM pointed at the wrong company, prefer fuzzy match.
            if company and _normalize(company) not in _normalize(app.company):
                better = _find_existing_application(db, company, title)
                if better is not None:
                    app = better
                    _enrich_application(app, company=company, title=title)
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
                status=suggestion.suggested_status,
                summary=suggestion.summary,
                source=source,
            )
    else:
        # status_change/note with no application_id — merge or create.
        app = _create_or_merge(
            db,
            company=company,
            title=title,
            status=suggestion.suggested_status or ApplicationStatus.applied,
            summary=suggestion.summary,
            source=source,
        )

    suggestion.status = SuggestionStatus.approved
    db.commit()
    return app
