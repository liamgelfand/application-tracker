import io
import zipfile


def test_backup_contains_database_and_key(client):
    client.post(
        "/api/applications",
        json={"company": "Acme", "title": "SWE", "status": "applied"},
    )

    r = client.get("/api/backup")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    archive = zipfile.ZipFile(io.BytesIO(r.content))
    assert "tracker.db" in archive.namelist()


def test_restore_replaces_current_data(client):
    client.post(
        "/api/applications",
        json={"company": "Original", "title": "SWE", "status": "applied"},
    )
    snapshot = client.get("/api/backup").content

    client.post(
        "/api/applications",
        json={"company": "AddedLater", "title": "PM", "status": "applied"},
    )
    assert len(client.get("/api/applications").json()) == 2

    r = client.post(
        "/api/backup/restore",
        files={"file": ("backup.zip", snapshot, "application/zip")},
    )
    assert r.status_code == 200

    companies = {a["company"] for a in client.get("/api/applications").json()}
    assert companies == {"Original"}


def test_restore_rejects_non_backup_zip(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")

    r = client.post(
        "/api/backup/restore",
        files={"file": ("bad.zip", buffer.getvalue(), "application/zip")},
    )
    assert r.status_code == 400


def test_restore_rejects_garbage(client):
    r = client.post(
        "/api/backup/restore",
        files={"file": ("bad.zip", b"not a zip at all", "application/zip")},
    )
    assert r.status_code == 400
