from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationStatus, EventSource, StatusEvent
from ..schemas import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationUpdate,
    MessageOut,
)

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
def get_application(app_id: int, db: Session = Depends(get_db)) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_id}", response_model=ApplicationDetailOut)
def update_application(
    app_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> Application:
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
    return app


@router.delete("/{app_id}", response_model=MessageOut)
def delete_application(app_id: int, db: Session = Depends(get_db)) -> MessageOut:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app)
    db.commit()
    return MessageOut(message="Application deleted")
