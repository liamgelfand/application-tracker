from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import decrypt, encrypt
from ..db import get_db
from ..models import EmailAccount, ProcessedEmail
from ..schemas import (
    ConnectionTestRequest,
    ConnectionTestResult,
    EmailAccountCreate,
    EmailAccountOut,
    EmailAccountUpdate,
    MessageOut,
)
from ..services.email import imap_client
from ..services.email.poller import sync_account

router = APIRouter(prefix="/api/email-accounts", tags=["email"])


@router.get("", response_model=list[EmailAccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[EmailAccount]:
    return list(db.execute(select(EmailAccount)).scalars().all())


@router.post("", response_model=EmailAccountOut, status_code=201)
def create_account(
    payload: EmailAccountCreate, db: Session = Depends(get_db)
) -> EmailAccount:
    data = payload.model_dump()
    password = data.pop("password")
    account = EmailAccount(**data, password_encrypted=encrypt(password))
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=EmailAccountOut)
def update_account(
    account_id: int, payload: EmailAccountUpdate, db: Session = Depends(get_db)
) -> EmailAccount:
    account = db.get(EmailAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            account.password_encrypted = encrypt(password)
    for key, value in data.items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", response_model=MessageOut)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> MessageOut:
    account = db.get(EmailAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
    return MessageOut(message="Account deleted")


@router.post("/test", response_model=ConnectionTestResult)
def test_connection(payload: ConnectionTestRequest) -> ConnectionTestResult:
    ok, message = imap_client.test_connection(
        host=payload.imap_host,
        port=payload.imap_port,
        username=payload.username,
        password=payload.password,
        use_ssl=payload.use_ssl,
        folder=payload.folder,
    )
    return ConnectionTestResult(ok=ok, message=message)


@router.post("/{account_id}/reset", response_model=MessageOut)
def reset_processed(account_id: int, db: Session = Depends(get_db)) -> MessageOut:
    """Roll back the last 10 processed emails so the next sync re-analyzes only recent mail."""
    account = db.get(EmailAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    # Find the 10 most recently processed emails ordered by UID descending.
    recent = (
        db.query(ProcessedEmail)
        .filter(ProcessedEmail.account_id == account_id)
        .order_by(ProcessedEmail.message_uid.desc())
        .limit(10)
        .all()
    )

    if not recent:
        return MessageOut(message="No processed emails to reset.")

    ids = [r.id for r in recent]
    uids = [int(r.message_uid) for r in recent if r.message_uid and r.message_uid.isdigit()]

    db.query(ProcessedEmail).filter(ProcessedEmail.id.in_(ids)).delete(
        synchronize_session=False
    )

    # Roll last_seen_uid back to just before the oldest of the deleted emails.
    if uids:
        account.last_seen_uid = min(uids) - 1 if min(uids) > 0 else None

    db.commit()
    return MessageOut(message=f"Reset {len(ids)} recent email(s). Next sync will re-analyze them.")


@router.post("/{account_id}/sync", response_model=dict)
def sync_now(account_id: int, db: Session = Depends(get_db)) -> dict:
    account = db.get(EmailAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not decrypt(account.password_encrypted):
        raise HTTPException(status_code=409, detail="Account has no stored password")
    try:
        stats = sync_account(db, account)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc
    return {"ok": True, "stats": stats}
