from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import func

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
from .status_inference import refine_suggested_status

# Pipeline order. Used to reject backwards moves when an older email is
# approved after a newer one.
STAGE_RANK = {
    ApplicationStatus.saved: 0,
    ApplicationStatus.applied: 1,
    ApplicationStatus.online_assessment: 2,
    ApplicationStatus.phone_screen: 3,
    ApplicationStatus.interview: 4,
    ApplicationStatus.offer: 5,
    ApplicationStatus.accepted: 6,
}
CLOSED_STATUSES = {
    ApplicationStatus.rejected,
    ApplicationStatus.ghosted,
    ApplicationStatus.accepted,
}

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


def _as_naive_utc(value: datetime | None) -> datetime | None:
    """Drop to naive UTC so values read back from SQLite stay comparable."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Exposed so duplicate detection in the API applies the same rules as matching.
normalize_label = _normalize
is_placeholder_title = _is_placeholder_title


def _conflicting_job_ids(app: Application, job_id: str | None) -> bool:
    """True when both sides name a req id and they disagree (different postings)."""
    return bool(job_id and app.job_id and app.job_id.strip() != job_id)


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

    jid = job_id.strip() if job_id else None
    has_title = bool(title) and not _is_placeholder_title(title)

    # 1. Same req id is the same posting, whatever the titles look like.
    if jid:
        for app in company_matches:
            if app.job_id and app.job_id.strip() == jid:
                return app

    # 2. Same role title, as long as req ids don't contradict each other.
    if has_title:
        for app in company_matches:
            if _conflicting_job_ids(app, jid):
                continue
            if _titles_match(app.title, title):
                return app

    # 3. Adopt a stub this pipeline created earlier from a thinner email
    #    ("Unknown" title) instead of opening a second row for one posting.
    adoptable = [
        a
        for a in company_matches
        if _is_placeholder_title(a.title) and not _conflicting_job_ids(a, jid)
    ]
    if len(adoptable) == 1:
        return adoptable[0]

    # 4. Nothing to distinguish roles by, and only one application here.
    if not jid and not has_title and len(company_matches) == 1:
        return company_matches[0]

    return None


def _latest_event_time(db: Session, app: Application) -> datetime | None:
    """Timestamp of the newest recorded evidence for this application."""
    return db.execute(
        select(func.max(StatusEvent.created_at)).where(
            StatusEvent.application_id == app.id
        )
    ).scalar_one_or_none()


def _is_forward_or_closing(
    prior: ApplicationStatus | None, new: ApplicationStatus
) -> bool:
    if new in CLOSED_STATUSES or prior is None:
        return True
    if prior in CLOSED_STATUSES:
        # Newer evidence after a rejection means the process actually reopened.
        return True
    return STAGE_RANK.get(new, 0) >= STAGE_RANK.get(prior, 0)


def _record_status(
    db: Session,
    app: Application,
    new_status: ApplicationStatus | None,
    *,
    note: str | None,
    source: EventSource,
    event_time: datetime,
) -> None:
    """Add timeline history, and move the current status only on newest evidence.

    Approving an older email after a newer one must not drag the card
    backwards (an application confirmation arriving after a rejection), but
    the stage it proves still belongs on the timeline at its own date.
    """
    if new_status is None or new_status == app.status:
        return

    prior = app.status
    event_time = _as_naive_utc(event_time) or _now_naive()
    latest = _as_naive_utc(_latest_event_time(db, app))
    is_newest = latest is None or event_time >= latest

    if is_newest and _is_forward_or_closing(prior, new_status):
        app.status = new_status
        db.add(
            StatusEvent(
                application_id=app.id,
                from_status=prior,
                to_status=new_status,
                note=note or "Updated from email",
                source=source,
                created_at=event_time,
            )
        )
        return

    # Stale or backwards evidence: keep the history, leave the card alone.
    db.add(
        StatusEvent(
            application_id=app.id,
            from_status=None,
            to_status=new_status,
            note=note or "Earlier email (status unchanged)",
            source=source,
            created_at=event_time,
        )
    )


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


_STATUS_ALIASES = {
    "assessment": "online_assessment",
    "online assessment": "online_assessment",
    "online_assessment": "online_assessment",
    "oa": "online_assessment",
    "coding_assessment": "online_assessment",
}


def _coerce_status(value: str | None) -> ApplicationStatus | None:
    if not value:
        return None
    raw = value.strip().lower().replace("-", "_")
    raw = _STATUS_ALIASES.get(raw, raw)
    try:
        return ApplicationStatus(raw)
    except ValueError:
        return None


def _enrich_application(
    app: Application,
    *,
    company: str | None,
    title: str | None,
    job_id: str | None = None,
) -> bool:
    """Fill missing/placeholder fields. Returns True when something changed."""
    changed = False
    if title and not _is_placeholder_title(title) and _is_placeholder_title(app.title):
        app.title = title
        changed = True
    if job_id and not app.job_id:
        app.job_id = job_id.strip()
        changed = True
    return changed


def _create_or_merge(
    db: Session,
    *,
    company: str | None,
    title: str | None,
    status: ApplicationStatus | None,
    summary: str | None,
    source: EventSource,
    job_id: str | None = None,
    event_time: datetime | None = None,
) -> Application | None:
    """Merge into a matching role or create a new application."""
    company = (company or "").strip() or None
    title = (title or "").strip() or None
    job_id = (job_id or "").strip() or None
    if _is_placeholder_title(title):
        title = None
    event_time = _as_naive_utc(event_time) or _now_naive()

    if not company:
        return None

    existing = _find_existing_application(db, company, title, job_id)
    if existing is not None:
        _enrich_application(existing, company=company, title=title, job_id=job_id)
        _record_status(
            db,
            existing,
            status,
            note=summary,
            source=source,
            event_time=event_time,
        )
        # An email that predates the row is evidence of when this actually began.
        created = _as_naive_utc(existing.created_at)
        applied = _as_naive_utc(existing.date_applied)
        if created and event_time < created:
            existing.created_at = event_time
            if applied is None or event_time < applied:
                existing.date_applied = event_time
        return existing

    app = Application(
        company=company,
        title=title or "Unknown",
        job_id=job_id,
        status=status or ApplicationStatus.applied,
        source="email",
        created_at=event_time,
        date_applied=event_time,
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
            created_at=event_time,
        )
    )
    return app


def build_suggestion_from_analysis(
    analysis: dict,
    *,
    sender: str,
    subject: str,
    snippet: str,
    email_date: datetime | None = None,
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

    suggested_status = refine_suggested_status(
        _coerce_status(analysis.get("suggested_status")),
        subject,
        analysis.get("summary"),
        snippet,
    )
    company = analysis.get("company") or _company_from_sender(sender)
    title = analysis.get("title")
    if _is_placeholder_title(title):
        title = None

    if (
        suggested_status is not None
        and kind == SuggestionKind.note
        and suggested_status
        in {
            ApplicationStatus.rejected,
            ApplicationStatus.online_assessment,
            ApplicationStatus.phone_screen,
            ApplicationStatus.interview,
            ApplicationStatus.offer,
        }
    ):
        kind = SuggestionKind.status_change


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
        email_date=email_date,
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
    else:
        refined = refine_suggested_status(
            suggestion.suggested_status,
            suggestion.email_subject,
            suggestion.summary,
            suggestion.email_snippet,
        )
        if refined is not None:
            suggestion.suggested_status = refined
            if (
                suggestion.kind == SuggestionKind.note
                and refined != ApplicationStatus.applied
            ):
                suggestion.kind = SuggestionKind.status_change

    company = payload.get("company") or _company_from_sender(suggestion.email_sender)
    title = payload.get("title")
    if _is_placeholder_title(title):
        title = None
    job_id = payload.get("job_id") or extract_job_id(
        suggestion.email_subject, suggestion.email_snippet
    )

    # Order the timeline by when the email was sent, not when the sync ran or
    # when you happened to click Approve.
    event_time = (
        _as_naive_utc(suggestion.email_date)
        or _as_naive_utc(suggestion.created_at)
        or _now_naive()
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
            event_time=event_time,
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
                        event_time=event_time,
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
            # Only status changes earn a timeline entry; the email itself is
            # already listed under the application's email activity.
            _record_status(
                db,
                app,
                suggestion.suggested_status
                if suggestion.kind == SuggestionKind.status_change
                else None,
                note=suggestion.summary,
                source=source,
                event_time=event_time,
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
                event_time=event_time,
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
            event_time=event_time,
        )

    suggestion.status = SuggestionStatus.approved
    db.commit()
    return app
