from app.db import SessionLocal
from app.models import (
    Application,
    ApplicationStatus,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)


def _make_suggestion(application_id: int | None, suggested_status) -> int:
    db = SessionLocal()
    try:
        s = Suggestion(
            application_id=application_id,
            kind=SuggestionKind.status_change,
            status=SuggestionStatus.pending,
            suggested_status=suggested_status,
            summary="Recruiter reached out",
            confidence=90,
            email_subject="Next steps",
            email_sender="recruiter@example.com",
            email_snippet="Let's schedule a call.",
        )
        db.add(s)
        db.commit()
        return s.id
    finally:
        db.close()


def test_approve_suggestion_updates_application(client):
    app = client.post(
        "/api/applications",
        json={"company": "Acme", "title": "SWE", "status": "applied"},
    ).json()
    sid = _make_suggestion(app["id"], ApplicationStatus.phone_screen)

    assert len(client.get("/api/suggestions?status=pending").json()) == 1

    r = client.post(f"/api/suggestions/{sid}/approve")
    assert r.status_code == 200

    updated = client.get(f"/api/applications/{app['id']}").json()
    assert updated["status"] == "phone_screen"
    assert len(client.get("/api/suggestions?status=pending").json()) == 0


def test_reject_suggestion(client):
    app = client.post(
        "/api/applications",
        json={"company": "Globex", "title": "PM", "status": "applied"},
    ).json()
    sid = _make_suggestion(app["id"], ApplicationStatus.interview)

    assert client.post(f"/api/suggestions/{sid}/reject").status_code == 200
    assert len(client.get("/api/suggestions?status=pending").json()) == 0
    # Application status is unchanged after a rejection.
    assert client.get(f"/api/applications/{app['id']}").json()["status"] == "applied"


def test_approve_with_overrides(client):
    sid = _make_suggestion(None, ApplicationStatus.applied)
    # Attach payload via approve overrides for a new application.
    from app.db import SessionLocal
    from app.models import Suggestion

    db = SessionLocal()
    try:
        s = db.get(Suggestion, sid)
        s.kind = SuggestionKind.new_application
        s.payload = '{"company": "WrongCo", "title": "Wrong"}'
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/suggestions/{sid}/approve",
        json={
            "company": "RightCo",
            "title": "Backend Engineer",
            "suggested_status": "applied",
        },
    )
    assert r.status_code == 200
    apps = client.get("/api/applications").json()
    match = [a for a in apps if a["company"] == "RightCo"]
    assert len(match) == 1
    assert match[0]["title"] == "Backend Engineer"


def test_approve_assessment_email_uses_online_assessment(client):
    app = client.post(
        "/api/applications",
        json={
            "company": "IBM",
            "title": "SWE Intern",
            "status": "applied",
            "job_id": "129919",
        },
    ).json()
    db = SessionLocal()
    try:
        s = Suggestion(
            application_id=app["id"],
            kind=SuggestionKind.status_change,
            status=SuggestionStatus.pending,
            suggested_status=ApplicationStatus.phone_screen,
            summary="IBM invited you to complete a coding assessment; update to phone_screen.",
            confidence=90,
            payload='{"company": "IBM", "title": "SWE Intern", "job_id": "129919"}',
            email_subject="Action Required:IBM Coding Assessment for completion Liam - 129919 - SWE Intern",
            email_sender="talent@ibm.com",
            email_snippet="Please complete your coding assessment within 7 days.",
        )
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()

    r = client.post(f"/api/suggestions/{sid}/approve")
    assert r.status_code == 200
    updated = client.get(f"/api/applications/{app['id']}").json()
    assert updated["status"] == "online_assessment"


def test_bulk_reject(client):
    app = client.post(
        "/api/applications",
        json={"company": "BulkCo", "title": "SWE", "status": "applied"},
    ).json()
    a = _make_suggestion(app["id"], ApplicationStatus.interview)
    b = _make_suggestion(app["id"], ApplicationStatus.offer)
    r = client.post("/api/suggestions/bulk-reject", json={"ids": [a, b]})
    assert r.status_code == 200
    assert len(client.get("/api/suggestions?status=pending").json()) == 0
