from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ParsedJob, ParseRequest
from ..services.llm.service import LLMError, LLMNotConfigured
from ..services.parser import parse_job_listing

router = APIRouter(prefix="/api/parse", tags=["parse"])


@router.post("", response_model=ParsedJob)
def parse(payload: ParseRequest, db: Session = Depends(get_db)) -> ParsedJob:
    try:
        return parse_job_listing(db, payload.text)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
