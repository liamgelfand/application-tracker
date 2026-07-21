from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from ..core.security import encrypt
from ..db import get_db
from ..models import LLMProvider
from ..schemas import (
    LLMProviderCreate,
    LLMProviderOut,
    LLMProviderUpdate,
    MessageOut,
    SettingsOut,
    SettingsUpdate,
)
from ..scheduler import reschedule as reschedule_poller
from ..services.settings_service import (
    get_auto_apply,
    get_poll_interval,
    set_auto_apply,
    set_poll_interval,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_out(provider: LLMProvider) -> LLMProviderOut:
    return LLMProviderOut(
        id=provider.id,
        name=provider.name,
        provider=provider.provider,
        model=provider.model,
        api_base=provider.api_base,
        is_active=provider.is_active,
        has_api_key=bool(provider.api_key_encrypted),
        created_at=provider.created_at,
    )


# ---------- App settings ----------
@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)) -> SettingsOut:
    return SettingsOut(
        email_poll_interval_seconds=get_poll_interval(
            db, app_settings.email_poll_interval_seconds
        ),
        auto_apply_suggestions=get_auto_apply(db),
    )


@router.patch("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate, db: Session = Depends(get_db)
) -> SettingsOut:
    if payload.auto_apply_suggestions is not None:
        set_auto_apply(db, payload.auto_apply_suggestions)
    if payload.email_poll_interval_seconds is not None:
        applied = set_poll_interval(db, payload.email_poll_interval_seconds)
        try:
            reschedule_poller(applied)
        except Exception:  # noqa: BLE001 - scheduler may not be running (e.g. tests)
            pass
    return SettingsOut(
        email_poll_interval_seconds=get_poll_interval(
            db, app_settings.email_poll_interval_seconds
        ),
        auto_apply_suggestions=get_auto_apply(db),
    )


# ---------- LLM providers ----------
@router.get("/llm-providers", response_model=list[LLMProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[LLMProviderOut]:
    providers = db.execute(select(LLMProvider)).scalars().all()
    return [_to_out(p) for p in providers]


@router.post("/llm-providers", response_model=LLMProviderOut, status_code=201)
def create_provider(
    payload: LLMProviderCreate, db: Session = Depends(get_db)
) -> LLMProviderOut:
    provider = LLMProvider(
        name=payload.name,
        provider=payload.provider,
        model=payload.model,
        api_base=payload.api_base,
        api_key_encrypted=encrypt(payload.api_key),
        is_active=payload.is_active,
    )
    db.add(provider)
    db.flush()
    if provider.is_active:
        _deactivate_others(db, provider.id)
    db.commit()
    db.refresh(provider)
    return _to_out(provider)


@router.patch("/llm-providers/{provider_id}", response_model=LLMProviderOut)
def update_provider(
    provider_id: int, payload: LLMProviderUpdate, db: Session = Depends(get_db)
) -> LLMProviderOut:
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        key = data.pop("api_key")
        if key:  # only replace when a non-empty key is provided
            provider.api_key_encrypted = encrypt(key)
    for key, value in data.items():
        setattr(provider, key, value)

    if provider.is_active:
        _deactivate_others(db, provider.id)
    db.commit()
    db.refresh(provider)
    return _to_out(provider)


@router.post("/llm-providers/{provider_id}/activate", response_model=LLMProviderOut)
def activate_provider(
    provider_id: int, db: Session = Depends(get_db)
) -> LLMProviderOut:
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider.is_active = True
    _deactivate_others(db, provider.id)
    db.commit()
    db.refresh(provider)
    return _to_out(provider)


@router.delete("/llm-providers/{provider_id}", response_model=MessageOut)
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> MessageOut:
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    db.delete(provider)
    db.commit()
    return MessageOut(message="Provider deleted")


def _deactivate_others(db: Session, keep_id: int) -> None:
    others = db.execute(
        select(LLMProvider).where(LLMProvider.id != keep_id, LLMProvider.is_active.is_(True))
    ).scalars().all()
    for other in others:
        other.is_active = False
