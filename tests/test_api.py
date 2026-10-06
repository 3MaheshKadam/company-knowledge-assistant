import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from conftest import DATA, make_settings

H = {"X-API-Key": "test-key-123"}


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def wait_job(client, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/v1/jobs/{job_id}", headers=H).json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(client, name: str):
    return client.post("/v1/documents", headers=H, files={"file": (name, (DATA / name).read_bytes())})


def test_health_is_public(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200


def test_auth_required(client):
    assert client.post("/v1/ask", json={"question": "leave days?"}).status_code == 401
    assert client.post("/v1/ask", json={"question": "leave days?"}, headers={"X-API-Key": "wrong"}).status_code == 401


def test_security_headers(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in r.headers


def test_full_flow_upload_ask_cache_paginate_delete(client):
    for name in ("hr_leave_policy.md", "employee_handbook.md", "expense_policy.txt"):
        r = upload(client, name)
        assert r.status_code == 202
        job = wait_job(client, r.json()["job_id"])
        assert job["status"] == "done" and job["result"]["chunks"] > 0

    # pagination
    p1 = client.get("/v1/documents?limit=2&offset=0", headers=H).json()
    assert p1["total"] == 3 and len(p1["items"]) == 2 and p1["next_offset"] == 2
    p2 = client.get("/v1/documents?limit=2&offset=2", headers=H).json()
    assert len(p2["items"]) == 1 and p2["next_offset"] is None
    assert client.get("/v1/documents?limit=0", headers=H).status_code == 422
    assert client.get("/v1/jobs?limit=2", headers=H).json()["total"] == 3

    # ask + cache
    body = {"question": "How many days of annual leave do full-time employees get?"}
    a1 = client.post("/v1/ask", json=body, headers=H).json()
    assert a1["grounded"] and "24" in a1["answer"] and a1["citations"][0]["source"] == "hr_leave_policy.md"
    assert a1["cached"] is False
    noisy = {"question": "  how many DAYS of annual leave do full-time employees get? "}
    a2 = client.post("/v1/ask", json=noisy, headers=H).json()
    assert a2["cached"] is True  # normalised key
    assert client.get("/v1/stats", headers=H).json()["cache"]["hits"] >= 1

    # ingest invalidates the cache (answers can change when data changes)
    wait_job(client, upload(client, "it_security_sop.md").json()["job_id"])
    assert client.post("/v1/ask", json=body, headers=H).json()["cached"] is False

    # delete
    assert client.delete("/v1/documents/expense_policy.txt", headers=H).json()["deleted_chunks"] > 0
    assert client.delete("/v1/documents/expense_policy.txt", headers=H).status_code == 404


def test_unanswerable_question_abstains(client):
    wait_job(client, upload(client, "hr_leave_policy.md").json()["job_id"])
    r = client.post("/v1/ask", json={"question": "What is the CEO's salary?"}, headers=H).json()
    assert r["grounded"] is False and r["citations"] == []


def test_upload_validation(client):
    bad = client.post("/v1/documents", headers=H, files={"file": ("evil.exe", b"MZ....")})
    assert bad.status_code == 415
    fake = client.post("/v1/documents", headers=H, files={"file": ("x.pdf", b"not really a pdf")})
    assert fake.status_code == 415


def test_path_traversal_filename_is_neutralised(client, tmp_path):
    r = client.post("/v1/documents", headers=H, files={"file": ("../../evil.txt", b"hello world policy")})
    assert r.status_code == 202
    wait_job(client, r.json()["job_id"])
    assert (tmp_path / "uploads" / "evil.txt").exists()
    assert not (tmp_path.parent / "evil.txt").exists()


def test_input_validation(client):
    assert client.post("/v1/ask", json={"question": "x"}, headers=H).status_code == 422
    assert client.post("/v1/ask", json={"question": "valid question", "mode": "bogus"}, headers=H).status_code == 422
    assert client.post("/v1/ask", json={"question": "q" * 1001}, headers=H).status_code == 422


def test_rate_limit_returns_429(tmp_path):
    from dataclasses import replace

    s = replace(make_settings(tmp_path), rate_limit_per_min=3)
    with TestClient(create_app(s)) as c:
        codes = [c.get("/v1/stats", headers=H).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_queue_full_gives_503(tmp_path):
    from dataclasses import replace

    s = replace(make_settings(tmp_path), queue_max_size=1, queue_workers=0)  # nothing drains
    with TestClient(create_app(s)) as c:
        first = upload(c, "expense_policy.txt")
        second = upload(c, "hr_leave_policy.md")
    assert first.status_code == 202 and second.status_code == 503 and second.headers["Retry-After"]
