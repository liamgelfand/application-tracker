from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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
