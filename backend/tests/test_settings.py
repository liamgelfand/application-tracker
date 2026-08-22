def test_default_settings(client):
    data = client.get("/api/settings").json()
    assert data["auto_apply_suggestions"] is False
    assert data["email_poll_interval_seconds"] == 900
    assert data["min_suggestion_confidence"] == 70
    assert data["follow_up_days"] == 14


def test_update_confidence_and_follow_up(client):
    r = client.patch(
        "/api/settings",
        json={"min_suggestion_confidence": 85, "follow_up_days": 21},
    )
    assert r.status_code == 200
    assert r.json()["min_suggestion_confidence"] == 85
    assert r.json()["follow_up_days"] == 21


def test_update_auto_apply(client):
    r = client.patch("/api/settings", json={"auto_apply_suggestions": True})
    assert r.json()["auto_apply_suggestions"] is True


def test_poll_interval_update_and_clamp(client):
    assert (
        client.patch(
            "/api/settings", json={"email_poll_interval_seconds": 1800}
        ).json()["email_poll_interval_seconds"]
        == 1800
    )
    # Below the minimum gets clamped to 60.
    assert (
        client.patch(
            "/api/settings", json={"email_poll_interval_seconds": 5}
        ).json()["email_poll_interval_seconds"]
        == 60
    )


def test_parse_without_provider_returns_409(client):
    r = client.post("/api/parse", json={"text": "Some job listing"})
    assert r.status_code == 409
