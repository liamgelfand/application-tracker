"""Duplicate detection must catch split rows without merging distinct reqs."""


def _add(client, **fields) -> dict:
    return client.post("/api/applications", json=fields).json()


def _pairs(client) -> set[frozenset[int]]:
    groups = client.get("/api/applications/duplicates").json()
    return {frozenset(a["id"] for a in g["applications"]) for g in groups}


def test_placeholder_title_row_is_flagged(client):
    stub = _add(client, company="Solace", title="Unknown", status="ghosted")
    real = _add(
        client,
        company="Solace",
        title="Associate Product Engineer (College Grad 2027)",
        status="rejected",
    )
    assert _pairs(client) == {frozenset({stub["id"], real["id"]})}


def test_reordered_title_is_flagged(client):
    a = _add(
        client,
        company="Northrop Grumman",
        title="Associate Software Engineer / Software Engineer (2027)",
        status="ghosted",
    )
    b = _add(
        client,
        company="Northrop Grumman",
        title="2027 Associate Software Engineer / Software Engineer",
        status="rejected",
        job_id="R10239590",
    )
    assert _pairs(client) == {frozenset({a["id"], b["id"]})}


def test_distinct_requisitions_are_never_flagged(client):
    _add(
        client,
        company="IBM",
        title="Software Developer Spring Co-op 2027",
        status="rejected",
        job_id="128506",
    )
    _add(
        client,
        company="IBM",
        title="Technical Sales Engineer - Entry-Level Sales Program 2027",
        status="rejected",
        job_id="128340",
    )
    _add(
        client,
        company="IBM",
        title="2027 Software Engineering Intern - Agentic AI",
        status="rejected",
        job_id="129919",
    )
    assert _pairs(client) == set()


def test_different_roles_without_job_ids_are_not_flagged(client):
    _add(
        client,
        company="P&G",
        title="Data & AI Engineering (2027 Grads)",
        status="rejected",
    )
    _add(
        client,
        company="P&G",
        title="IT Engineering (Software, Platform, & Network) (2027 Grads)",
        status="rejected",
    )
    assert _pairs(client) == set()


def test_same_job_id_is_flagged(client):
    a = _add(client, company="Cigna", title="TECDP Track A", job_id="26010470")
    b = _add(client, company="Cigna", title="Something Else", job_id="26010470")
    assert _pairs(client) == {frozenset({a["id"], b["id"]})}


def test_merge_keeps_job_id_and_beats_ghosted(client):
    ghost = _add(
        client,
        company="Northrop Grumman",
        title="Associate Software Engineer (2027)",
        status="ghosted",
    )
    real = _add(
        client,
        company="Northrop Grumman",
        title="Unknown",
        status="rejected",
        job_id="R10239590",
    )

    # Merge the richer row into the ghosted one: direction must not lose data.
    merged = client.post(
        "/api/applications/merge",
        json={"source_id": real["id"], "target_id": ghost["id"]},
    ).json()

    assert merged["status"] == "rejected", "a real outcome outranks ghosted"
    assert merged["job_id"] == "R10239590", "job id must survive the merge"
    assert merged["title"] == "Associate Software Engineer (2027)"
    assert len(client.get("/api/applications").json()) == 1
