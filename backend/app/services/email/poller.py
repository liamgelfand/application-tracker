from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.security import decrypt
from ...db import SessionLocal
from ...models import EmailAccount, ProcessedEmail
from .. import sync_progress
from ..llm.service import LLMError, get_active_provider
from ..settings_service import get_auto_apply, get_min_confidence
from ..suggestion_service import apply_suggestion, build_suggestion_from_analysis
from . import imap_client
from .analyzer import analyze_email

logger = logging.getLogger("tracker.poller")

# Abort the rest of a sync after this many LLM failures so we don't burn
# through the UID window while Ollama/API is down.
_MAX_LLM_FAILURES = 2


def sync_account(
    db: Session,
    account: EmailAccount,
    *,
    fetch_limit: int = 25,
) -> dict:
    """Fetch and analyze new mail for one account. Returns a small stats dict."""
    stats = {
        "fetched": 0,
        "job_related": 0,
        "suggestions": 0,
        "applied": 0,
        "low_confidence": 0,
        "llm_failures": 0,
        "aborted": False,
    }

    password = decrypt(account.password_encrypted)
    if not password:
        logger.warning("Account %s has no stored password; skipping.", account.id)
        stats["skipped"] = "no_password"
        sync_progress.fail("Account has no stored password")
        return stats

    if get_active_provider(db) is None:
        logger.warning(
            "No active LLM provider — skipping sync for account %s so mail isn't lost.",
            account.id,
        )
        sync_progress.fail("No active LLM provider configured. Add one in Settings.")
        stats["skipped"] = "no_llm"
        return stats

    try:
        emails, _fetch_max_uid = imap_client.fetch_new_emails(
            host=account.imap_host,
            port=account.imap_port,
            username=account.username,
            password=password,
            use_ssl=account.use_ssl,
            folder=account.folder,
            last_seen_uid=account.last_seen_uid,
            limit=fetch_limit,
        )
    except Exception as exc:  # noqa: BLE001
        sync_progress.fail(str(exc))
        raise

    # Process in UID order so we can advance last_seen only through a
    # contiguous success prefix (failures must not skip ahead).
    emails = sorted(emails, key=lambda m: m.uid)

    stats["fetched"] = len(emails)
    sync_progress.start(account.id, account.name, len(emails))

    auto_apply = get_auto_apply(db)
    min_confidence = get_min_confidence(db)

    # Only move the cursor past emails we've fully handled with no earlier gap.
    advance_to = account.last_seen_uid
    saw_failure = False

    for idx, msg in enumerate(emails, start=1):
        already = db.execute(
            select(ProcessedEmail).where(
                ProcessedEmail.account_id == account.id,
                ProcessedEmail.message_uid == str(msg.uid),
            )
        ).scalar_one_or_none()
        if already:
            if not saw_failure:
                advance_to = msg.uid
            continue

        sync_progress.tick(idx, subject=msg.subject)
        logger.info(
            "Analyzing uid=%s subject=%r from=%r", msg.uid, msg.subject, msg.sender
        )

        # End the read transaction before analyze/LLM so API requests aren't blocked.
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

        is_job_related = False
        llm_failed = False
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

        if analysis is None:
            # No LLM for a non-fastpath email — leave unprocessed for retry.
            llm_failed = True
            analysis = {}

        if not llm_failed and analysis:
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
            conf = analysis.get("confidence")
            if conf is not None and int(conf) < min_confidence:
                logger.info(
                    "uid=%s below confidence gate (%s < %s) — no suggestion",
                    msg.uid, conf, min_confidence,
                )
                stats["low_confidence"] += 1
            else:
                suggestion = build_suggestion_from_analysis(
                    analysis,
                    sender=msg.sender,
                    subject=msg.subject,
                    snippet=msg.body,
                    email_date=msg.received_at,
                )
                if suggestion is not None:
                    db.add(suggestion)
                    db.flush()
                    stats["suggestions"] += 1
                    if auto_apply:
                        apply_suggestion(db, suggestion)
                        stats["applied"] += 1

        # If the LLM failed / couldn't classify, don't mark as processed and
        # don't advance last_seen_uid past this message.
        if llm_failed:
            saw_failure = True
            stats["llm_failures"] += 1
            if stats["llm_failures"] >= _MAX_LLM_FAILURES:
                logger.error(
                    "Aborting sync after %s LLM failures — remaining mail kept for retry",
                    stats["llm_failures"],
                )
                stats["aborted"] = True
                sync_progress.fail(
                    "LLM unavailable — emails left unprocessed for the next sync. "
                    "Check Settings → AI Providers (Claude active?)."
                )
                break
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
        if not saw_failure:
            advance_to = msg.uid

    account.last_seen_uid = advance_to
    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    if not stats["aborted"]:
        sync_progress.finish(
            f"Done — {stats['suggestions']} suggestion(s) from {stats['fetched']} email(s)."
        )
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
