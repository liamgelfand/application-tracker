from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Suggestion, SuggestionStatus
from ..schemas import MessageOut, SuggestionOut
from ..services.suggestion_service import apply_suggestion

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(
    status: SuggestionStatus | None = SuggestionStatus.pending,
    db: Session = Depends(get_db),
) -> list[Suggestion]:
    stmt = select(Suggestion)
    if status is not None:
        stmt = stmt.where(Suggestion.status == status)
    stmt = stmt.order_by(Suggestion.created_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("/{suggestion_id}/approve", response_model=MessageOut)
def approve_suggestion(suggestion_id: int, db: Session = Depends(get_db)) -> MessageOut:
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != SuggestionStatus.pending:
        raise HTTPException(status_code=409, detail="Suggestion already resolved")
    apply_suggestion(db, suggestion)
    return MessageOut(message="Suggestion approved and applied")


@router.post("/{suggestion_id}/reject", response_model=MessageOut)
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db)) -> MessageOut:
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = SuggestionStatus.rejected
    db.commit()
    return MessageOut(message="Suggestion rejected")
