from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Suggestion, SuggestionStatus
from ..schemas import (
    MessageOut,
    SuggestionApproveIn,
    SuggestionBulkIn,
    SuggestionOut,
)
from ..services.suggestion_service import apply_suggestion

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


def _to_out(suggestion: Suggestion) -> SuggestionOut:
    payload: dict = {}
    if suggestion.payload:
        try:
            payload = json.loads(suggestion.payload)
        except json.JSONDecodeError:
            payload = {}
    return SuggestionOut(
        id=suggestion.id,
        application_id=suggestion.application_id,
        kind=suggestion.kind,
        status=suggestion.status,
        suggested_status=suggestion.suggested_status,
        summary=suggestion.summary,
        confidence=suggestion.confidence,
        company=payload.get("company"),
        title=payload.get("title"),
        job_id=payload.get("job_id"),
        email_subject=suggestion.email_subject,
        email_sender=suggestion.email_sender,
        email_snippet=suggestion.email_snippet,
        email_date=suggestion.email_date,
        created_at=suggestion.created_at,
    )


def _chronological(suggestion: Suggestion):
    """Sort key: when the email was sent, falling back to when we saw it."""
    return (suggestion.email_date or suggestion.created_at, suggestion.id)


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(
    status: SuggestionStatus | None = SuggestionStatus.pending,
    db: Session = Depends(get_db),
) -> list[SuggestionOut]:
    stmt = select(Suggestion)
    if status is not None:
        stmt = stmt.where(Suggestion.status == status)
    rows = list(db.execute(stmt).scalars().all())
    # Oldest email first: an application confirmation should be reviewed before
    # the rejection that answered it, or approving them rebuilds a bad timeline.
    rows.sort(key=_chronological)
    return [_to_out(s) for s in rows]


@router.post("/bulk-approve", response_model=MessageOut)
def bulk_approve(
    payload: SuggestionBulkIn, db: Session = Depends(get_db)
) -> MessageOut:
    pending = [
        s
        for s in (db.get(Suggestion, sid) for sid in payload.ids)
        if s is not None and s.status == SuggestionStatus.pending
    ]
    # Apply in email order regardless of the order ids arrived in.
    pending.sort(key=_chronological)
    for suggestion in pending:
        apply_suggestion(db, suggestion)
    return MessageOut(message=f"Approved {len(pending)} suggestion(s)")


@router.post("/bulk-reject", response_model=MessageOut)
def bulk_reject(
    payload: SuggestionBulkIn, db: Session = Depends(get_db)
) -> MessageOut:
    count = 0
    for sid in payload.ids:
        suggestion = db.get(Suggestion, sid)
        if suggestion is None or suggestion.status != SuggestionStatus.pending:
            continue
        suggestion.status = SuggestionStatus.rejected
        count += 1
    db.commit()
    return MessageOut(message=f"Dismissed {count} suggestion(s)")


@router.post("/{suggestion_id}/approve", response_model=MessageOut)
def approve_suggestion(
    suggestion_id: int,
    payload: SuggestionApproveIn = SuggestionApproveIn(),
    db: Session = Depends(get_db),
) -> MessageOut:
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != SuggestionStatus.pending:
        raise HTTPException(status_code=409, detail="Suggestion already resolved")
    apply_suggestion(
        db,
        suggestion,
        company_override=payload.company,
        title_override=payload.title,
        status_override=payload.suggested_status,
    )
    return MessageOut(message="Suggestion approved and applied")


@router.post("/{suggestion_id}/reject", response_model=MessageOut)
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db)) -> MessageOut:
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = SuggestionStatus.rejected
    db.commit()
    return MessageOut(message="Suggestion rejected")
