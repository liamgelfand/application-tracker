def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_application_crud_and_timeline(client):
    # Create
    r = client.post(
        "/api/applications",
        json={"company": "Acme", "title": "SWE", "status": "applied"},
    )
    assert r.status_code == 201
    app_id = r.json()["id"]
    assert r.json()["status"] == "applied"

    # List
    assert len(client.get("/api/applications").json()) == 1

    # Detail includes the creation event
    detail = client.get(f"/api/applications/{app_id}").json()
    assert len(detail["events"]) == 1

    # Status change adds a timeline event
    r = client.patch(
        f"/api/applications/{app_id}",
        json={"status": "interview", "status_note": "scheduled"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "interview"
    assert len(r.json()["events"]) == 2

    # Search
    assert len(client.get("/api/applications?search=acme").json()) == 1
    assert len(client.get("/api/applications?search=nope").json()) == 0

    # Delete
    assert client.delete(f"/api/applications/{app_id}").status_code == 200
    assert len(client.get("/api/applications").json()) == 0


def test_get_missing_application_returns_404(client):
    assert client.get("/api/applications/9999").status_code == 404
