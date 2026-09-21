def _create(client, company, status, **extra):
    payload = {"company": company, "title": "Role", "status": status, **extra}
    return client.post("/api/applications", json=payload).json()


def test_analytics_rates(client):
    _create(client, "A", "applied")
    _create(client, "B", "interview")
    _create(client, "C", "rejected")
    _create(client, "D", "saved")  # not submitted

    data = client.get("/api/analytics").json()
    assert data["total"] == 4
    assert data["submitted"] == 3  # excludes the "saved" one
    # responded = interview + rejected = 2 of 3 submitted
    assert data["response_rate"] == round(100 * 2 / 3, 1)
    # advanced (phone_screen+) = interview = 1 of 3
    assert data["interview_rate"] == round(100 * 1 / 3, 1)
    assert data["status_counts"]["saved"] == 1
    assert len(data["over_time"]) == 8
    assert [step["stage"] for step in data["funnel"]] == [
        "submitted",
        "responded",
        "online_assessment",
        "interview",
        "offer",
    ]
    assert data["funnel"][0]["count"] == 3
    assert data["funnel"][3]["count"] == 1


def test_online_assessment_is_a_response_not_an_interview(client):
    _create(client, "A", "applied")
    _create(client, "B", "online_assessment")
    data = client.get("/api/analytics").json()
    assert data["status_counts"]["online_assessment"] == 1
    assert data["response_rate"] == 50.0
    assert data["oa_rate"] == 50.0
    assert data["interview_rate"] == 0.0


def test_phone_screen_is_not_an_interview(client):
    _create(client, "A", "applied")
    _create(client, "B", "phone_screen")
    data = client.get("/api/analytics").json()
    assert data["interview_rate"] == 0.0
    assert data["response_rate"] == 50.0


def test_assessment_mislabeled_as_interview_counts_as_oa(client):
    app = _create(client, "IBM", "applied")
    client.patch(
        f"/api/applications/{app['id']}",
        json={
            "status": "interview",
            "status_note": "IBM has invited you to complete a coding assessment",
        },
    )
    client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})

    data = client.get("/api/analytics").json()
    assert data["oa_rate"] == 100.0
    assert data["oa_count"] == 1
    assert data["interview_rate"] == 0.0
    assert data["interview_count"] == 0


def test_email_confirmation_labeled_interview_is_not_an_interview(client):
    app = _create(client, "Bending Spoons", "applied")
    client.patch(
        f"/api/applications/{app['id']}",
        json={
            "status": "interview",
            "status_note": "New application confirmation from Bending Spoons for a Graduate AI role.",
        },
    )
    # Source is manual for PATCH — simulate email by checking OA invite path instead:
    # a confirmation without live-interview language should not count when emailed.
    from app.db import SessionLocal
    from app.models import EventSource, StatusEvent

    db = SessionLocal()
    ev = (
        db.query(StatusEvent)
        .filter(StatusEvent.application_id == app["id"], StatusEvent.to_status != None)  # noqa: E711
        .order_by(StatusEvent.id.desc())
        .first()
    )
    ev.source = EventSource.email
    db.commit()
    db.close()

    client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})
    data = client.get("/api/analytics").json()
    assert data["interview_rate"] == 0.0
    assert data["interview_count"] == 0


def test_live_interview_invite_still_counts_as_interview(client):
    app = _create(client, "Wolverine", "applied")
    client.patch(
        f"/api/applications/{app['id']}",
        json={
            "status": "interview",
            "status_note": "Wolverine has scheduled an interview for the role",
        },
    )
    client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})

    data = client.get("/api/analytics").json()
    assert data["interview_rate"] == 100.0
    assert data["interview_count"] == 1


def test_interview_then_rejected_still_counts_as_interview(client):
    app = _create(client, "Acme", "interview")
    client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})

    data = client.get("/api/analytics").json()
    assert data["submitted"] == 1
    assert data["status_counts"]["rejected"] == 1
    assert data["status_counts"]["interview"] == 0
    assert data["response_rate"] == 100.0
    assert data["interview_rate"] == 100.0
    assert data["interview_count"] == 1
    assert data["offer_rate"] == 0.0
    assert data["rejection_by_stage"] == [
        {"stage": "applied", "count": 0},
        {"stage": "online_assessment", "count": 0},
        {"stage": "phone_screen", "count": 0},
        {"stage": "interview", "count": 1},
        {"stage": "offer", "count": 0},
    ]


def test_offer_then_rejected_still_counts_as_offer(client):
    app = _create(client, "Globex", "offer")
    client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})

    data = client.get("/api/analytics").json()
    assert data["offer_rate"] == 100.0
    assert data["interview_rate"] == 100.0
    assert data["response_rate"] == 100.0


def test_ghosted_after_interview_still_counts_as_response(client):
    app = _create(client, "Initech", "applied")
    client.patch(f"/api/applications/{app['id']}", json={"status": "interview"})
    client.patch(f"/api/applications/{app['id']}", json={"status": "ghosted"})

    data = client.get("/api/analytics").json()
    assert data["ghost_rate"] == 100.0
    assert data["response_rate"] == 100.0
    assert data["interview_rate"] == 100.0


def test_analytics_groups_by_source_and_company(client):
    _create(client, "Acme", "interview", source="LinkedIn")
    _create(client, "Acme", "applied", source="LinkedIn")
    _create(client, "Globex", "rejected", source="Referral")

    data = client.get("/api/analytics").json()
    by_source = {row["source"]: row for row in data["by_source"]}
    assert by_source["LinkedIn"]["submitted"] == 2
    assert by_source["LinkedIn"]["interview_rate"] == 50.0
    assert by_source["Referral"]["submitted"] == 1

    by_company = {row["company"]: row for row in data["by_company"]}
    assert by_company["Acme"]["submitted"] == 2
    assert by_company["Acme"]["interviews"] == 1


def test_analytics_empty(client):
    data = client.get("/api/analytics").json()
    assert data["total"] == 0
    assert data["response_rate"] == 0.0
    assert data["avg_days_to_response"] is None
    assert data["avg_days_to_interview"] is None
    assert data["funnel"][0]["count"] == 0
    assert data["by_source"] == []
    assert data["by_company"] == []
