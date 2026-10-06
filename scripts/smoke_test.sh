#!/usr/bin/env bash
# End-to-end smoke test against a RUNNING service (used by CI against the built container).
# Usage: scripts/smoke_test.sh [base_url] <api_key> [document]
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
KEY="${2:?usage: smoke_test.sh [base_url] <api_key> [document]}"
DOC="${3:-data/raw/hr_leave_policy.md}"
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

echo "1/6 health"
for _ in $(seq 1 40); do curl -fsS "$BASE/healthz" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "$BASE/healthz" | json "['status']" | grep -q ok || fail "healthz"

echo "2/6 auth is enforced"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/v1/ask" -H 'content-type: application/json' -d '{"question":"leave days"}')
[ "$code" = "401" ] || fail "expected 401 without key, got $code"

echo "3/6 upload is queued (202)"
resp=$(curl -sS -w '\n%{http_code}' -H "X-API-Key: $KEY" -F "file=@$DOC" "$BASE/v1/documents")
[ "$(echo "$resp" | tail -1)" = "202" ] || fail "upload expected 202: $resp"
job=$(echo "$resp" | head -1 | json "['job_id']")

echo "4/6 job completes"
for _ in $(seq 1 60); do
  st=$(curl -fsS -H "X-API-Key: $KEY" "$BASE/v1/jobs/$job" | json "['status']")
  [ "$st" = "done" ] && break
  [ "$st" = "failed" ] && fail "ingest job failed"
  sleep 0.5
done
[ "$st" = "done" ] || fail "job did not finish"

echo "5/6 grounded answer with citation"
q='{"question":"How many days of annual leave do full-time employees get?"}'
ans=$(curl -fsS -H "X-API-Key: $KEY" -H 'content-type: application/json' -d "$q" "$BASE/v1/ask")
echo "$ans" | json "['grounded']" | grep -q True || fail "not grounded: $ans"
echo "$ans" | grep -q '24' || fail "wrong answer: $ans"
echo "$ans" | json "['citations'][0]['source']" | grep -q hr_leave_policy.md || fail "bad citation"

echo "6/6 repeat question is served from cache"
curl -fsS -H "X-API-Key: $KEY" -H 'content-type: application/json' -d "$q" "$BASE/v1/ask" | json "['cached']" | grep -q True || fail "cache miss"

echo "SMOKE OK"
