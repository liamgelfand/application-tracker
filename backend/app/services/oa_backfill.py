"""One-time backfill: move apps with OA evidence into online_assessment."""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Application,
    ApplicationStatus,
    EventSource,
    ProcessedEmail,
    Setting,
    StatusEvent,
    Suggestion,
)
from .status_inference import (
    looks_like_live_interview,
    looks_like_online_assessment,
    looks_like_phone_screen,
    looks_like_rejection,
)
from .suggestion_service import (
    _find_existing_application,
    _is_placeholder_title,
    _normalize,
    _titles_match,
)

logger = logging.getLogger("tracker.oa_backfill")

BACKFILL_KEY = "oa_backfill_v1"

_ELIGIBLE = {ApplicationStatus.applied, ApplicationStatus.phone_screen}


def run_online_assessment_backfill(db: Session, *, force: bool = False) -> int:
    """Upgrade applied/phone_screen apps that already received an OA email.

    Skips rejected/ghosted/interview+ (current status is more accurate) and
    skips phone_screen rows that also have a real recruiter-call signal.
    """
    existing = db.get(Setting, BACKFILL_KEY)
    if existing and existing.value == "done" and not force:
        return 0

    apps = list(db.execute(select(Application)).scalars().all())
    events = list(db.execute(select(StatusEvent)).scalars().all())
    suggestions = list(db.execute(select(Suggestion)).scalars().all())
    emails = list(
        db.execute(
            select(ProcessedEmail).where(ProcessedEmail.is_job_related.is_(True))
        ).scalars().all()
    )
    apps_by_id = {a.id: a for a in apps}

    events_by_app: dict[int, list[StatusEvent]] = defaultdict(list)
    for ev in events:
        events_by_app[ev.application_id].append(ev)

    sug_by_app: dict[int, list[Suggestion]] = defaultdict(list)
    for s in suggestions:
        if s.application_id is not None:
            sug_by_app[s.application_id].append(s)

    oa_app_ids: set[int] = set()

    for app in apps:
        blobs: list[str] = []
        for ev in events_by_app.get(app.id, []):
            blobs.append(ev.note or "")
        for s in sug_by_app.get(app.id, []):
            blobs.append(
                " ".join(
                    x
                    for x in (
                        s.email_subject,
                        s.email_sender,
                        s.email_snippet,
                        s.summary,
                    )
                    if x
                )
            )
        combined = " ".join(blobs)
        if looks_like_rejection(combined) or looks_like_live_interview(combined):
            continue
        if looks_like_online_assessment(combined):
            oa_app_ids.add(app.id)

    for s in suggestions:
        parts = (s.email_subject, s.email_sender, s.email_snippet, s.summary)
        if looks_like_rejection(*parts) or looks_like_live_interview(*parts):
            continue
        if not looks_like_online_assessment(*parts):
            continue
        target = _resolve_suggestion_app(db, apps_by_id, s)
        if target is not None:
            oa_app_ids.add(target.id)

    for pe in emails:
        if re.search(
            r"result of (?:your )?assessment", pe.subject or "", re.IGNORECASE
        ):
            continue
        if not looks_like_online_assessment(pe.subject, pe.sender):
            continue
        if looks_like_rejection(pe.subject, pe.sender):
            continue
        if looks_like_live_interview(pe.subject, pe.sender):
            continue
        for app in _match_apps_to_email(apps, pe.sender or "", pe.subject or ""):
            oa_app_ids.add(app.id)

    updated = 0
    for app in apps:
        if app.id not in oa_app_ids or app.status not in _ELIGIBLE:
            continue
        if app.status == ApplicationStatus.phone_screen and _has_real_phone_screen(
            events_by_app.get(app.id, []), sug_by_app.get(app.id, [])
        ):
            continue
        old = app.status
        app.status = ApplicationStatus.online_assessment
        db.add(
            StatusEvent(
                application_id=app.id,
                from_status=old,
                to_status=app.status,
                note="Backfilled to Online Assessment from existing assessment emails",
                source=EventSource.system,
            )
        )
        updated += 1
        logger.info(
            "OA backfill: #%s %s — %s (%s → online_assessment)",
            app.id,
            app.company,
            app.title,
            old.value,
        )

    for s in suggestions:
        if s.status is None or s.status.value != "pending":
            continue
        blob_parts = (s.email_subject, s.email_sender, s.email_snippet, s.summary)
        if looks_like_rejection(*blob_parts) or looks_like_live_interview(*blob_parts):
            continue
        if not looks_like_online_assessment(*blob_parts):
            continue
        if s.suggested_status in (
            None,
            ApplicationStatus.applied,
            ApplicationStatus.phone_screen,
            ApplicationStatus.saved,
        ):
            s.suggested_status = ApplicationStatus.online_assessment

    if existing:
        existing.value = "done"
    else:
        db.add(Setting(key=BACKFILL_KEY, value="done"))
    db.commit()
    logger.info("OA backfill complete: updated %s application(s)", updated)
    return updated


def _payload(suggestion: Suggestion) -> dict:
    if not suggestion.payload:
        return {}
    try:
        data = json.loads(suggestion.payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_suggestion_app(
    db: Session,
    apps_by_id: dict[int, Application],
    suggestion: Suggestion,
) -> Application | None:
    payload = _payload(suggestion)
    company = payload.get("company")
    if company:
        role_match = _find_existing_application(
            db,
            company,
            payload.get("title"),
            payload.get("job_id"),
        )
        if role_match is not None and role_match.status in _ELIGIBLE:
            return role_match
    if suggestion.application_id is not None:
        linked = apps_by_id.get(suggestion.application_id)
        if linked is not None and linked.status in _ELIGIBLE:
            return linked
    return None


def _has_real_phone_screen(
    events: list[StatusEvent], suggestions: list[Suggestion]
) -> bool:
    for ev in events:
        if looks_like_phone_screen(ev.note or ""):
            return True
    for s in suggestions:
        if looks_like_phone_screen(
            s.email_subject, s.email_sender, s.email_snippet, s.summary
        ):
            return True
    return False


def _match_apps_to_email(
    apps: list[Application], sender: str, subject: str
) -> list[Application]:
    blob = f"{sender} {subject}"
    if not _normalize(blob):
        return []

    company_hits = [a for a in apps if _company_mentioned(a.company, blob)]
    if not company_hits:
        return []

    titled = []
    for a in company_hits:
        if a.job_id and a.job_id in (subject or ""):
            titled.append(a)
            continue
        if not _is_placeholder_title(a.title) and _titles_match(a.title, subject):
            titled.append(a)
    if titled:
        return titled

    eligible = [a for a in company_hits if a.status in _ELIGIBLE]
    if len(eligible) == 1:
        return eligible
    return []


def _company_mentioned(company: str | None, blob: str) -> bool:
    n = _normalize(company or "")
    if not n or len(n) < 2:
        return False
    nb = _normalize(blob)
    if not nb:
        return False
    return bool(re.search(rf"\b{re.escape(n)}\b", nb))
