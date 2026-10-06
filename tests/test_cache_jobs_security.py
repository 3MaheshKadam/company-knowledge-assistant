import time

import pytest
from fastapi import HTTPException

from api.cache import TTLCache
from api.jobs import DONE, FAILED, JobQueue, QueueFull
from api.pagination import paginate
from api.security import RateLimiter, check_api_key, sanitize_filename, validate_upload


def test_cache_ttl_and_lru():
    c = TTLCache(max_items=2, ttl_s=0.05)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # evicts "a"
    assert c.get("a") is None and c.get("c") == 3
    time.sleep(0.07)
    assert c.get("c") is None
    assert c.stats()["misses"] >= 2


def test_pagination_bounds():
    items = list(range(25))
    p = paginate(items, limit=10, offset=20)
    assert p["items"] == [20, 21, 22, 23, 24] and p["next_offset"] is None and p["total"] == 25
    assert paginate(items, 10, 0)["next_offset"] == 10
    assert len(paginate(list(range(500)), 9999, 0)["items"]) == 100  # capped


def test_job_queue_runs_and_isolates_failures():
    q = JobQueue(workers=1, max_size=5)
    q.start()
    ok = q.submit("t", lambda: {"x": 1})
    bad = q.submit("t", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    after = q.submit("t", lambda: {"y": 2})
    deadline = time.time() + 3
    while time.time() < deadline and not all(j.finished_at for j in (ok, bad, after)):
        time.sleep(0.01)
    q.stop()
    assert ok.status == DONE and bad.status == FAILED and "boom" in bad.error and after.status == DONE


def test_job_queue_backpressure():
    q = JobQueue(workers=1, max_size=1)  # workers not started => nothing drains
    q.submit("t", lambda: {})
    with pytest.raises(QueueFull):
        q.submit("t", lambda: {})


def test_api_key_checks():
    assert check_api_key("k1", ("k1", "k2"), False)
    with pytest.raises(HTTPException) as e:
        check_api_key("bad", ("k1",), False)
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        check_api_key(None, (), False)
    assert e.value.status_code == 503  # secure by default: no keys configured => refuse
    assert check_api_key(None, (), True) == "anonymous"


def test_rate_limiter():
    rl = RateLimiter(per_minute=2)
    assert rl.allow("c")[0] and rl.allow("c")[0]
    allowed, retry = rl.allow("c")
    assert not allowed and retry > 0
    assert rl.allow("other")[0]  # per-client buckets


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"),
    ("..\\..\\windows\\evil.txt", "evil.txt"),
    ("my report (final).pdf", "my_report_final_.pdf"),
    ("", "upload"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_validate_upload_rules():
    assert validate_upload("a.txt", b"hello", 100) == "a.txt"
    for name, data, code in [
        ("a.exe", b"MZ", 415),
        ("a.pdf", b"not a pdf", 415),
        ("a.txt", b"", 400),
        ("a.txt", b"x" * 200, 413),
        ("a.md", b"\x00\x01binary", 415),
    ]:
        with pytest.raises(HTTPException) as e:
            validate_upload(name, data, 100)
        assert e.value.status_code == code, name
