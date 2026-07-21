def test_provider_key_is_masked(client):
    r = client.post(
        "/api/settings/llm-providers",
        json={
            "name": "OpenAI",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-secret",
            "is_active": True,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["has_api_key"] is True
    assert "api_key" not in body  # the raw key is never returned
    assert body["is_active"] is True


def test_active_provider_is_exclusive(client):
    p1 = client.post(
        "/api/settings/llm-providers",
        json={"name": "P1", "provider": "ollama", "model": "llama3.1", "is_active": True},
    ).json()
    p2 = client.post(
        "/api/settings/llm-providers",
        json={"name": "P2", "provider": "ollama", "model": "mistral", "is_active": True},
    ).json()

    providers = {p["id"]: p for p in client.get("/api/settings/llm-providers").json()}
    assert providers[p1["id"]]["is_active"] is False
    assert providers[p2["id"]]["is_active"] is True

    # Re-activate the first one.
    client.post(f"/api/settings/llm-providers/{p1['id']}/activate")
    providers = {p["id"]: p for p in client.get("/api/settings/llm-providers").json()}
    assert providers[p1["id"]]["is_active"] is True
    assert providers[p2["id"]]["is_active"] is False


def test_delete_provider(client):
    p = client.post(
        "/api/settings/llm-providers",
        json={"name": "Temp", "provider": "ollama", "model": "llama3.1"},
    ).json()
    assert client.delete(f"/api/settings/llm-providers/{p['id']}").status_code == 200
    assert client.get("/api/settings/llm-providers").json() == []
