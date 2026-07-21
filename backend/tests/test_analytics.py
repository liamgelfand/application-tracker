def _create(client, company, status):
    client.post(
        "/api/applications",
        json={"company": company, "title": "Role", "status": status},
    )


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


def test_analytics_empty(client):
    data = client.get("/api/analytics").json()
    assert data["total"] == 0
    assert data["response_rate"] == 0.0
    assert data["avg_days_to_response"] is None
