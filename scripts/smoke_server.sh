#!/usr/bin/env bash
# Smoke test dashboard serverja (CI + lokalno):
#   health / command / /api/agenda + zaščita API-ja (ROB_API_TOKEN → 401/200).
# V CI ni certs/ → HTTP; lokalno (certi obstajajo) → HTTPS (curl -k).
set -euo pipefail
cd "$(dirname "$0")/.."

SCHEME="http"
[ -f certs/cert.pem ] && [ -f certs/key.pem ] && SCHEME="https"
BASE="${SCHEME}://127.0.0.1:8787"
CURL="curl -sk"   # -k: self-signed; HTTP ga ignorira

# Port mora biti prost, sicer bi health padel na NAPAK server (stari proces).
if curl -sk -o /dev/null "$BASE/api/health" 2>/dev/null; then
  echo "✗ port $PORT ni prost (že teče server?) — ubij ga in ponovi." >&2
  exit 1
fi

wait_up() {
  for _ in $(seq 1 20); do
    code=$($CURL -o /dev/null -w "%{http_code}" "$BASE/api/health" 2>/dev/null || true)
    [ "$code" = "200" ] && return 0
    sleep 1
  done
  echo "  ✗ server se ni zagnal (zadnji health=$code)" >&2
  tail -20 /tmp/dash_smoke.log >&2 || true
  return 1
}

echo "── 1 · server BREZ tokena (shema: $SCHEME) ──"
ROB_API_TOKEN='' bun run src/server.ts > /tmp/dash_smoke.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
wait_up
h1=$($CURL -o /dev/null -w "%{http_code}" "$BASE/api/health")
echo "  health:            $h1"      && [ "$h1" = "200" ]
c1=$($CURL -o /dev/null -w "%{http_code}" "$BASE/command")
echo "  /command (UI):     $c1"      && [ "$c1" = "200" ]
a1=$($CURL -o /dev/null -w "%{http_code}" "$BASE/api/agenda")
echo "  /api/agenda:       $a1"      && [ "$a1" = "200" ]
r1=$($CURL -o /dev/null -w "%{http_code} %{redirect_url}" "$BASE/")
echo "  / → redirect:      $r1"
[ "${r1%% *}" = "302" ] && [[ "$r1" == *"/command"* ]]
kill $PID 2>/dev/null || true
sleep 1

echo "── 2 · server Z ROB_API_TOKEN (zaščita) ──"
ROB_API_TOKEN="smoke-test-token" bun run src/server.ts > /tmp/dash_smoke2.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
wait_up
u1=$($CURL -o /dev/null -w "%{http_code}" "$BASE/api/agenda")
echo "  agenda brez cookie (401): $u1"  && [ "$u1" = "401" ]
b1=$($CURL -o /dev/null -w "%{http_code}" -X POST "$BASE/api/auth" -H "Content-Type: application/json" -d '{"token":"napačen"}')
echo "  auth napačen (401):      $b1"  && [ "$b1" = "401" ]
$CURL -c /tmp/dash_smoke_cj.txt -o /dev/null -X POST "$BASE/api/auth" -H "Content-Type: application/json" -d '{"token":"smoke-test-token"}'
a2=$($CURL -b /tmp/dash_smoke_cj.txt -o /dev/null -w "%{http_code}" "$BASE/api/agenda")
echo "  agenda s cookie (200):   $a2"  && [ "$a2" = "200" ]
kill $PID 2>/dev/null || true
rm -f /tmp/dash_smoke_cj.txt

echo "✅ SMOKE TEST OK"
