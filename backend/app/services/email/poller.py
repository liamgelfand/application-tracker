from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.security import decrypt
from ...db import SessionLocal
from ...models import EmailAccount, ProcessedEmail
from ..llm.service import LLMError, get_active_provider
from ..settings_service import get_auto_apply
from ..suggestion_service import apply_suggestion, build_suggestion_from_analysis
from . import imap_client
from .analyzer import analyze_email

logger = logging.getLogger("tracker.poller")


def sync_account(db: Session, account: EmailAccount) -> dict:
    """Fetch and analyze new mail for one account. Returns a small stats dict."""
    stats = {"fetched": 0, "job_related": 0, "suggestions": 0, "applied": 0}

    password = decrypt(account.password_encrypted)
    if not password:
        logger.warning("Account %s has no stored password; skipping.", account.id)
        stats["skipped"] = "no_password"
        return stats

    # Without an active LLM provider we cannot classify mail. Skip entirely so
    # emails are left untouched (not marked processed) and analyzed once a
    # provider is configured.
    if get_active_provider(db) is None:
        logger.info(
            "Account %s: no active LLM provider; skipping analysis.", account.id
        )
        stats["skipped"] = "no_llm"
        return stats

    emails, max_uid = imap_client.fetch_new_emails(
        host=account.imap_host,
        port=account.imap_port,
        username=account.username,
        password=password,
        use_ssl=account.use_ssl,
        folder=account.folder,
        last_seen_uid=account.last_seen_uid,
    )
    stats["fetched"] = len(emails)

    auto_apply = get_auto_apply(db)
    llm_ready = True

    for msg in emails:
        already = db.execute(
            select(ProcessedEmail).where(
                ProcessedEmail.account_id == account.id,
                ProcessedEmail.message_uid == str(msg.uid),
            )
        ).scalar_one_or_none()
        if already:
            continue

        logger.info(
            "Analyzing uid=%s subject=%r from=%r", msg.uid, msg.subject, msg.sender
        )

        is_job_related = False
        llm_failed = False
        if llm_ready:
            try:
                analysis = analyze_email(
                    db, sender=msg.sender, subject=msg.subject, body=msg.body
                )
            except LLMError as exc:
                logger.warning(
                    "LLM analysis failed for uid %s (%r): %s — will retry next sync",
                    msg.uid, msg.subject, exc,
                )
                llm_failed = True
                analysis = {}

            if not llm_failed:
                logger.info(
                    "uid=%s → is_job_related=%s kind=%s confidence=%s summary=%r",
                    msg.uid,
                    analysis.get("is_job_related"),
                    analysis.get("kind"),
                    analysis.get("confidence"),
                    analysis.get("summary"),
                )

            if analysis.get("is_job_related"):
                is_job_related = True
                stats["job_related"] += 1
                suggestion = build_suggestion_from_analysis(
                    analysis,
                    sender=msg.sender,
                    subject=msg.subject,
                    snippet=msg.body,
                )
                if suggestion is not None:
                    db.add(suggestion)
                    db.flush()
                    stats["suggestions"] += 1
                    if auto_apply:
                        apply_suggestion(db, suggestion)
                        stats["applied"] += 1

        # If the LLM failed, don't mark as processed — it will be retried next sync.
        if llm_failed:
            continue

        db.add(
            ProcessedEmail(
                account_id=account.id,
                message_uid=str(msg.uid),
                message_id=msg.message_id,
                subject=msg.subject,
                sender=msg.sender,
                received_at=msg.received_at,
                is_job_related=is_job_related,
            )
        )
        db.commit()

    account.last_seen_uid = max_uid
    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return stats


def sync_all_accounts() -> None:
    """Scheduler entry point: sync every active account."""
    db = SessionLocal()
    try:
        accounts = (
            db.execute(select(EmailAccount).where(EmailAccount.active.is_(True)))
            .scalars()
            .all()
        )
        for account in accounts:
            try:
                stats = sync_account(db, account)
                logger.info("Synced account %s: %s", account.name, stats)
            except Exception as exc:  # noqa: BLE001 - keep the scheduler alive
                logger.exception("Failed to sync account %s: %s", account.id, exc)
    finally:
        db.close()
