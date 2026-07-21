def test_csv_import_and_export(client):
    csv_data = "company,title,status\nAcme,SWE,applied\nGlobex,PM,interview\n"
    r = client.post(
        "/api/applications/import",
        files={"file": ("apps.csv", csv_data, "text/csv")},
    )
    assert r.status_code == 200
    assert "2" in r.json()["message"]
    assert len(client.get("/api/applications").json()) == 2

    csv_out = client.get("/api/applications/export?format=csv")
    assert csv_out.status_code == 200
    assert "Acme" in csv_out.text
    assert "Globex" in csv_out.text

    json_out = client.get("/api/applications/export?format=json")
    assert json_out.status_code == 200
    assert len(json_out.json()) == 2


def test_json_import(client):
    payload = [{"company": "Initech", "title": "Engineer", "status": "offer"}]
    import json

    r = client.post(
        "/api/applications/import",
        files={"file": ("apps.json", json.dumps(payload), "application/json")},
    )
    assert r.status_code == 200
    apps = client.get("/api/applications").json()
    assert len(apps) == 1
    assert apps[0]["status"] == "offer"


def test_import_skips_empty_rows(client):
    csv_data = "company,title,status\n,,\nReal,Dev,saved\n"
    r = client.post(
        "/api/applications/import",
        files={"file": ("apps.csv", csv_data, "text/csv")},
    )
    assert r.status_code == 200
    assert len(client.get("/api/applications").json()) == 1
