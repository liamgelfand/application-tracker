"""Review-queue ordering, job matching, and timeline construction."""

from datetime import datetime

from app.db import SessionLocal
from app.models import (
    Application,
    ApplicationStatus,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)

AUG22 = datetime(2026, 8, 22, 9, 0)
AUG26 = datetime(2026, 8, 26, 14, 0)
SEP02 = datetime(2026, 9, 2, 11, 0)


def _suggestion(
    *,
    kind: SuggestionKind,
    company: str,
    title: str | None,
    status: ApplicationStatus | None,
    email_date: datetime,
    subject: str = "Update",
    summary: str = "Email update",
    job_id: str | None = None,
    application_id: int | None = None,
) -> int:
    import json

    db = SessionLocal()
    try:
        s = Suggestion(
            application_id=application_id,
            kind=kind,
            status=SuggestionStatus.pending,
            suggested_status=status,
            summary=summary,
            confidence=95,
            payload=json.dumps(
                {"company": company, "title": title, "job_id": job_id}
            ),
            email_subject=subject,
            email_sender=f"careers@{company.lower().replace(' ', '')}.com",
            email_snippet=summary,
            email_date=email_date,
        )
        db.add(s)
        db.commit()
        return s.id
    finally:
        db.close()


def _events(client, app_id: int) -> list[tuple[str | None, str | None]]:
    detail = client.get(f"/api/applications/{app_id}").json()
    return [(e["from_status"], e["to_status"]) for e in detail["events"]]


def test_queue_lists_oldest_email_first(client):
    newer = _suggestion(
        kind=SuggestionKind.status_change,
        company="Wolverine",
        title="C++ Engineer",
        status=ApplicationStatus.rejected,
        email_date=AUG26,
        subject="Your application",
    )
    older = _suggestion(
        kind=SuggestionKind.new_application,
        company="Wolverine",
        title="C++ Engineer",
        status=ApplicationStatus.applied,
        email_date=AUG22,
        subject="We received your application",
    )

    queue = client.get("/api/suggestions?status=pending").json()
    assert [s["id"] for s in queue] == [older, newer]


def test_older_confirmation_approved_last_does_not_undo_rejection(client):
    """The reported bug: accept the change, then accept the card creation."""
    rejection = _suggestion(
        kind=SuggestionKind.status_change,
        company="Wolverine",
        title="C++ Engineer",
        status=ApplicationStatus.rejected,
        email_date=AUG26,
        summary="Moving forward with other candidates.",
    )
    confirmation = _suggestion(
        kind=SuggestionKind.new_application,
        company="Wolverine",
        title="C++ Engineer",
        status=ApplicationStatus.applied,
        email_date=AUG22,
        summary="Application received.",
    )

    assert client.post(f"/api/suggestions/{rejection}/approve").status_code == 200
    assert client.post(f"/api/suggestions/{confirmation}/approve").status_code == 200

    apps = client.get("/api/applications").json()
    assert len(apps) == 1, "the confirmation must not open a second row"
    app = apps[0]
    assert app["status"] == "rejected", "an older email must not reopen the card"

    # Both stages are on the timeline, newest first.
    detail = client.get(f"/api/applications/{app['id']}").json()
    tos = [e["to_status"] for e in detail["events"]]
    assert tos == ["rejected", "applied"]
    stamps = [e["created_at"] for e in detail["events"]]
    assert stamps == sorted(stamps, reverse=True), "timeline must be chronological"
    # The card is backdated to the confirmation email, not to approval time.
    assert app["date_applied"].startswith("2026-08-22")


def test_real_title_adopts_unknown_stub_instead_of_duplicating(client):
    stub = _suggestion(
        kind=SuggestionKind.new_application,
        company="Shell",
        title=None,
        status=ApplicationStatus.applied,
        email_date=AUG22,
        summary="Thanks for applying.",
    )
    client.post(f"/api/suggestions/{stub}/approve")

    apps = client.get("/api/applications").json()
    assert len(apps) == 1
    assert apps[0]["title"] == "Unknown"

    named = _suggestion(
        kind=SuggestionKind.new_application,
        company="Shell",
        title="Graduate Program 2027",
        status=ApplicationStatus.online_assessment,
        email_date=AUG26,
        summary="Complete your assessment.",
    )
    client.post(f"/api/suggestions/{named}/approve")

    apps = client.get("/api/applications").json()
    assert len(apps) == 1, "the named email should fill in the stub"
    assert apps[0]["title"] == "Graduate Program 2027"
    assert apps[0]["status"] == "online_assessment"


def test_different_job_ids_stay_separate_applications(client):
    first = _suggestion(
        kind=SuggestionKind.new_application,
        company="IBM",
        title="Software Developer Co-op",
        status=ApplicationStatus.applied,
        email_date=AUG22,
        job_id="128506",
    )
    second = _suggestion(
        kind=SuggestionKind.new_application,
        company="IBM",
        title="Technical Sales Engineer",
        status=ApplicationStatus.applied,
        email_date=AUG26,
        job_id="128340",
    )
    client.post(f"/api/suggestions/{first}/approve")
    client.post(f"/api/suggestions/{second}/approve")

    apps = client.get("/api/applications").json()
    assert len(apps) == 2
    assert {a["job_id"] for a in apps} == {"128506", "128340"}


def test_forward_progress_from_newer_email_still_applies(client):
    created = _suggestion(
        kind=SuggestionKind.new_application,
        company="Bending Spoons",
        title="Graduate AI Engineer",
        status=ApplicationStatus.applied,
        email_date=AUG22,
    )
    client.post(f"/api/suggestions/{created}/approve")
    app_id = client.get("/api/applications").json()[0]["id"]

    advance = _suggestion(
        kind=SuggestionKind.status_change,
        company="Bending Spoons",
        title="Graduate AI Engineer",
        status=ApplicationStatus.interview,
        email_date=SEP02,
        application_id=app_id,
        summary="We would like to schedule an interview.",
    )
    client.post(f"/api/suggestions/{advance}/approve")

    assert client.get(f"/api/applications/{app_id}").json()["status"] == "interview"
    assert ("applied", "interview") in _events(client, app_id)


def test_plain_note_does_not_clutter_the_timeline(client):
    app = client.post(
        "/api/applications",
        json={"company": "Initech", "title": "SWE", "status": "applied"},
    ).json()
    before = len(_events(client, app["id"]))

    note = _suggestion(
        kind=SuggestionKind.note,
        company="Initech",
        title="SWE",
        status=None,
        email_date=SEP02,
        application_id=app["id"],
        summary="Acknowledgement of your accommodation request.",
    )
    client.post(f"/api/suggestions/{note}/approve")

    assert len(_events(client, app["id"])) == before, "notes are not status changes"


def test_bulk_approve_applies_in_email_order(client):
    rejection = _suggestion(
        kind=SuggestionKind.status_change,
        company="Carrier",
        title="Digital Technology Program",
        status=ApplicationStatus.rejected,
        email_date=SEP02,
    )
    confirmation = _suggestion(
        kind=SuggestionKind.new_application,
        company="Carrier",
        title="Digital Technology Program",
        status=ApplicationStatus.applied,
        email_date=AUG22,
    )

    # Ids deliberately passed newest-first.
    r = client.post(
        "/api/suggestions/bulk-approve",
        json={"ids": [rejection, confirmation]},
    )
    assert r.status_code == 200

    apps = client.get("/api/applications").json()
    assert len(apps) == 1
    assert apps[0]["status"] == "rejected"
