from app.db import SessionLocal
from app.models import (
    ApplicationStatus,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)
from app.services.oa_backfill import run_online_assessment_backfill


def test_backfill_promotes_applied_oa_and_skips_rejected(client):
    applied = client.post(
        "/api/applications",
        json={"company": "IBM", "title": "SWE Intern", "status": "applied"},
    ).json()
    rejected = client.post(
        "/api/applications",
        json={"company": "P&G", "title": "IT Engineer", "status": "rejected"},
    ).json()

    db = SessionLocal()
    try:
        db.add(
            Suggestion(
                application_id=applied["id"],
                kind=SuggestionKind.status_change,
                status=SuggestionStatus.approved,
                suggested_status=ApplicationStatus.phone_screen,
                summary="IBM coding assessment invitation; update to phone_screen.",
                email_subject=(
                    "Action Required:IBM Coding Assessment for completion "
                    "Liam - 129919 - SWE Intern"
                ),
                email_sender="talent@ibm.com",
            )
        )
        db.add(
            Suggestion(
                application_id=rejected["id"],
                kind=SuggestionKind.status_change,
                status=SuggestionStatus.approved,
                suggested_status=ApplicationStatus.rejected,
                summary="P&G rejected after online assessment.",
                email_subject="P&G Careers – Result of your Assessment",
                email_sender="pgworkdaysystem.im@pg.com",
            )
        )
        db.commit()
        n = run_online_assessment_backfill(db, force=True)
    finally:
        db.close()

    assert n >= 1
    assert client.get(f"/api/applications/{applied['id']}").json()["status"] == (
        "online_assessment"
    )
    assert client.get(f"/api/applications/{rejected['id']}").json()["status"] == (
        "rejected"
    )


def test_backfill_does_not_override_real_phone_screen(client):
    app = client.post(
        "/api/applications",
        json={"company": "Acme", "title": "SWE", "status": "phone_screen"},
    ).json()
    db = SessionLocal()
    try:
        db.add(
            Suggestion(
                application_id=app["id"],
                kind=SuggestionKind.status_change,
                status=SuggestionStatus.approved,
                suggested_status=ApplicationStatus.phone_screen,
                summary="Recruiter wants to schedule an intro call this week.",
                email_subject="Intro call with Acme recruiting",
                email_sender="recruiter@acme.com",
            )
        )
        db.commit()
        run_online_assessment_backfill(db, force=True)
    finally:
        db.close()

    assert client.get(f"/api/applications/{app['id']}").json()["status"] == (
        "phone_screen"
    )


def test_backfill_relabels_phone_screen_that_was_only_an_oa(client):
    app = client.post(
        "/api/applications",
        json={"company": "Solace", "title": "Associate SWE", "status": "phone_screen"},
    ).json()
    db = SessionLocal()
    try:
        db.add(
            Suggestion(
                application_id=app["id"],
                kind=SuggestionKind.status_change,
                status=SuggestionStatus.approved,
                suggested_status=ApplicationStatus.phone_screen,
                summary="Solace invited you to complete a CodeSignal assessment.",
                email_subject=(
                    "Solace invited you to complete Solace Associate Software "
                    "Engineer Assignment on CodeSignal"
                ),
                email_sender="no-reply@codesignal.com",
            )
        )
        db.commit()
        run_online_assessment_backfill(db, force=True)
    finally:
        db.close()

    assert client.get(f"/api/applications/{app['id']}").json()["status"] == (
        "online_assessment"
    )
