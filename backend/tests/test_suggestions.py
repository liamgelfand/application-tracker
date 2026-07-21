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
