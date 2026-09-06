from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Application,
    ApplicationStatus,
    EventSource,
    ProcessedEmail,
    StatusEvent,
    Suggestion,
)
from ..schemas import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationUpdate,
    EmailActivityOut,
    MergeApplicationsIn,
    MessageOut,
    StatusEventOut,
)
from ..services.settings_service import get_follow_up_days

router = APIRouter(prefix="/api/applications", tags=["applications"])

EXPORT_FIELDS = [
    "company",
    "title",
    "location",
    "url",
    "source",
    "salary",
    "status",
    "skills",
    "notes",
    "contact_email",
    "date_applied",
    "description",
]


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: ApplicationStatus | None = None,
    search: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[Application]:
    stmt = select(Application)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Application.company.ilike(like),
                Application.title.ilike(like),
                Application.location.ilike(like),
            )
        )
    stmt = stmt.order_by(Application.updated_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(
    payload: ApplicationCreate, db: Session = Depends(get_db)
) -> Application:
    app = Application(**payload.model_dump())
    db.add(app)
    db.flush()
    db.add(
        StatusEvent(
            application_id=app.id,
            from_status=None,
            to_status=app.status,
            note="Application created",
            source=EventSource.manual,
        )
    )
    db.commit()
    db.refresh(app)
    return app


@router.get("/export")
def export_applications(
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: Session = Depends(get_db),
) -> Response:
    apps = db.execute(
        select(Application).order_by(Application.created_at.asc())
    ).scalars().all()

    def _value(app: Application, field: str) -> str:
        val = getattr(app, field)
        if isinstance(val, ApplicationStatus):
            return val.value
        if isinstance(val, datetime):
            return val.isoformat()
        return "" if val is None else str(val)

    stamp = datetime.now().strftime("%Y%m%d")
    if format == "json":
        payload = [{f: _value(a, f) for f in EXPORT_FIELDS} for a in apps]
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=applications-{stamp}.json"
            },
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for a in apps:
        writer.writerow({f: _value(a, f) for f in EXPORT_FIELDS})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=applications-{stamp}.csv"
        },
    )


def _coerce_status(value: str | None) -> ApplicationStatus:
    if not value:
        return ApplicationStatus.saved
    try:
        return ApplicationStatus(value.strip().lower())
    except ValueError:
        return ApplicationStatus.saved


def _coerce_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for parse in (datetime.fromisoformat,):
        try:
            return parse(value)
        except ValueError:
            continue
    return None


_FOLLOW_UP_STATUSES = {
    ApplicationStatus.applied,
    ApplicationStatus.online_assessment,
    ApplicationStatus.phone_screen,
    ApplicationStatus.interview,
}


def _normalize_company(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# Too generic to safely substring-match against all inbox subjects.
_GENERIC_COMPANY_MATCH = {
    "entry",
    "level",
    "software",
    "engineer",
    "intern",
    "new",
    "grad",
    "team",
    "careers",
    "jobs",
    "hr",
    "talent",
}


def _related_emails(db: Session, app: Application) -> list[EmailActivityOut]:
    items: list[EmailActivityOut] = []
    suggestions = db.execute(
        select(Suggestion)
        .where(Suggestion.application_id == app.id)
        .order_by(Suggestion.created_at.desc())
    ).scalars().all()
    for s in suggestions:
        items.append(
            EmailActivityOut(
                id=s.id,
                kind="suggestion",
                subject=s.email_subject,
                sender=s.email_sender,
                snippet=s.email_snippet,
                summary=s.summary,
                suggestion_status=s.status,
                is_job_related=True,
                created_at=s.created_at,
            )
        )

    # Fuzzy inbox match only for distinctive company names (never "Entry").
    norm = _normalize_company(app.company or "")
    if norm and len(norm) >= 5 and norm not in _GENERIC_COMPANY_MATCH:
        recent = db.execute(
            select(ProcessedEmail)
            .where(ProcessedEmail.is_job_related.is_(True))
            .order_by(ProcessedEmail.created_at.desc())
            .limit(200)
        ).scalars().all()
        seen_subjects = {
            (i.subject or "").strip().lower() for i in items if i.subject
        }
        # Prefer whole-token match so "entry" doesn't hit "entry-level" spam.
        token = re.compile(rf"\b{re.escape(norm)}\b", re.IGNORECASE)
        for pe in recent:
            blob = f"{pe.subject or ''} {pe.sender or ''}"
            if not token.search(_normalize_company(blob)) and not token.search(blob):
                continue
            key = (pe.subject or "").strip().lower()
            if key and key in seen_subjects:
                continue
            items.append(
                EmailActivityOut(
                    id=pe.id,
                    kind="processed_email",
                    subject=pe.subject,
                    sender=pe.sender,
                    snippet=None,
                    summary=None,
                    suggestion_status=None,
                    is_job_related=pe.is_job_related,
                    created_at=pe.created_at,
                )
            )
            if key:
                seen_subjects.add(key)

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:40]


def _detail_out(db: Session, app: Application) -> ApplicationDetailOut:
    return ApplicationDetailOut(
        id=app.id,
        company=app.company,
        title=app.title,
        location=app.location,
        url=app.url,
        source=app.source,
        salary=app.salary,
        status=app.status,
        description=app.description,
        skills=app.skills,
        notes=app.notes,
        contact_email=app.contact_email,
        job_id=app.job_id,
        date_applied=app.date_applied,
        created_at=app.created_at,
        updated_at=app.updated_at,
        events=[StatusEventOut.model_validate(e) for e in (app.events or [])],
        related_emails=_related_emails(db, app),
    )


@router.get("/reminders", response_model=list[ApplicationOut])
def list_follow_up_reminders(db: Session = Depends(get_db)) -> list[Application]:
    """Applications awaiting a reply longer than the configured follow-up window."""
    days = get_follow_up_days(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    apps = db.execute(
        select(Application)
        .where(Application.status.in_(_FOLLOW_UP_STATUSES))
        .order_by(Application.updated_at.asc())
    ).scalars().all()
    due: list[Application] = []
    for app in apps:
        updated = app.updated_at
        if updated is None:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if updated <= cutoff:
            due.append(app)
    return due


@router.post("/merge", response_model=ApplicationDetailOut)
def merge_applications(
    payload: MergeApplicationsIn, db: Session = Depends(get_db)
) -> ApplicationDetailOut:
    """Merge source into target: move events/suggestions, enrich fields, delete source."""
    if payload.source_id == payload.target_id:
        raise HTTPException(status_code=400, detail="Cannot merge an application into itself")
    source = db.get(Application, payload.source_id)
    target = db.get(Application, payload.target_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Application not found")

    for event in list(source.events):
        event.application_id = target.id
    for suggestion in list(source.suggestions):
        suggestion.application_id = target.id

    # Prefer non-placeholder title/company and fill empty optional fields.
    if (not target.title or target.title.lower() == "unknown") and source.title:
        target.title = source.title
    if source.location and not target.location:
        target.location = source.location
    if source.url and not target.url:
        target.url = source.url
    if source.salary and not target.salary:
        target.salary = source.salary
    if source.notes:
        target.notes = (
            f"{target.notes}\n\n--- merged ---\n{source.notes}".strip()
            if target.notes
            else source.notes
        )
    if source.description and not target.description:
        target.description = source.description
    if source.skills and not target.skills:
        target.skills = source.skills
    if source.contact_email and not target.contact_email:
        target.contact_email = source.contact_email
    if source.date_applied and (
        not target.date_applied or source.date_applied < target.date_applied
    ):
        target.date_applied = source.date_applied

    db.add(
        StatusEvent(
            application_id=target.id,
            from_status=target.status,
            to_status=target.status,
            note=f"Merged application #{source.id} ({source.company} — {source.title})",
            source=EventSource.system,
        )
    )
    db.delete(source)
    db.commit()
    db.refresh(target)
    return _detail_out(db, target)


@router.post("/import", response_model=MessageOut)
async def import_applications(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> MessageOut:
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    filename = (file.filename or "").lower()

    rows: list[dict] = []
    if filename.endswith(".json") or raw.lstrip().startswith(("[", "{")):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        rows = data if isinstance(data, list) else [data]
    else:
        rows = list(csv.DictReader(io.StringIO(raw)))

    imported = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = (row.get("company") or "").strip()
        title = (row.get("title") or "").strip()
        if not company and not title:
            continue
        app = Application(
            company=company or "Unknown",
            title=title or "Unknown",
            location=(row.get("location") or None),
            url=(row.get("url") or None),
            source=(row.get("source") or None),
            salary=(row.get("salary") or None),
            status=_coerce_status(row.get("status")),
            skills=(row.get("skills") or None),
            notes=(row.get("notes") or None),
            contact_email=(row.get("contact_email") or None),
            date_applied=_coerce_date(row.get("date_applied")),
            description=(row.get("description") or None),
        )
        db.add(app)
        db.flush()
        db.add(
            StatusEvent(
                application_id=app.id,
                from_status=None,
                to_status=app.status,
                note="Imported",
                source=EventSource.system,
            )
        )
        imported += 1

    db.commit()
    return MessageOut(message=f"Imported {imported} application(s).")


@router.get("/{app_id}", response_model=ApplicationDetailOut)
def get_application(
    app_id: int, db: Session = Depends(get_db)
) -> ApplicationDetailOut:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _detail_out(db, app)


@router.patch("/{app_id}", response_model=ApplicationDetailOut)
def update_application(
    app_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> ApplicationDetailOut:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    data = payload.model_dump(exclude_unset=True)
    status_note = data.pop("status_note", None)
    new_status = data.get("status")

    if new_status is not None and new_status != app.status:
        db.add(
            StatusEvent(
                application_id=app.id,
                from_status=app.status,
                to_status=new_status,
                note=status_note or "Status updated",
                source=EventSource.manual,
            )
        )

    for key, value in data.items():
        setattr(app, key, value)

    db.commit()
    db.refresh(app)
    return _detail_out(db, app)


@router.delete("/{app_id}", response_model=MessageOut)
def delete_application(app_id: int, db: Session = Depends(get_db)) -> MessageOut:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app)
    db.commit()
    return MessageOut(message="Application deleted")
