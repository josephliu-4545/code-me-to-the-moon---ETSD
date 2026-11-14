#!/usr/bin/env bash
# Smoke-test the production container without any credentials (no live NASA or Earth Engine calls).
# Usage: scripts/container-smoke-test.sh [image]   (default image: estd:local; build it first)
# Runs locally (Git Bash / Linux / macOS) and in CI.
set -euo pipefail

IMAGE="${1:-estd:local}"
PORT="${SMOKE_PORT:-18080}"
BASE="http://127.0.0.1:${PORT}"
FAILURES=0
CONTAINER=""

pass() { printf '  PASS  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
check() { if eval "$2"; then pass "$1"; else fail "$1"; fi; }

start() {
  stop
  CONTAINER=$(docker run -d --rm -p "${PORT}:8080" "$@" "$IMAGE")
  for _ in $(seq 1 60); do
    curl -fsS "${BASE}/" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "container did not start"; docker logs "$CONTAINER" || true; exit 1
}
stop() { if [ -n "$CONTAINER" ]; then docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; CONTAINER=""; fi; }
trap stop EXIT

# Status code only (body discarded in the shell, not by curl, so it behaves the same on Windows Git Bash).
code() { curl -s -w '%{http_code}' --max-time "${2:-30}" "${BASE}$1" -o - 2>/dev/null | tail -c 3 || true; }
body() { curl -s --max-time "${2:-30}" "${BASE}$1" || true; }
code_with_header() { curl -s -w '%{http_code}' --max-time 30 -H "$2" "${BASE}$1" -o - 2>/dev/null | tail -c 3 || true; }

echo "== Image contents"
check "runs as a non-root user" '[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != "0" ]'
check "no development reload in the start command" '! docker inspect -f "{{json .Config.Cmd}}" "$IMAGE" | grep -q -- "--reload"'
check "single worker" 'docker inspect -f "{{json .Config.Cmd}}" "$IMAGE" | grep -q -- "--workers 1"'
check "no Node.js or test tooling in the runtime image" '! docker run --rm --entrypoint sh "$IMAGE" -c "command -v node || command -v npm || python -c \"import pytest\"" >/dev/null 2>&1'
check "no .env files or credential files in the image" \
  '[ -z "$(docker run --rm --entrypoint sh "$IMAGE" -c "find / -xdev \( -name .env -o -name \"*.env\" -o -name \"*credentials*.json\" -o -name \"*service-account*.json\" -o -name \"*.pem\" -o -name \"*.p12\" \) -not -path \"/proc/*\" -not -path \"/usr/*\" -not -path \"/etc/ssl/*\" 2>/dev/null")" ]'
check "no tests, docs or virtual environments copied" \
  '[ -z "$(docker run --rm --entrypoint sh "$IMAGE" -c "ls -d /srv/backend/tests /srv/backend/.venv /srv/docs /srv/frontend/node_modules 2>/dev/null")" ]'

echo "== Single origin, no Earth Engine configuration"
start -e EE_PROJECT_ID=
check "service root responds" '[ "$(code /)" = 200 ]'
check "frontend served at /app/" 'body /app/ | grep -qi "<!doctype html"'
ASSET=$(body /app/ | grep -o '/app/assets/[^"]*\.js' | head -1 || true)
check "index references assets under /app/" '[ -n "$ASSET" ]'
check "static JavaScript asset loads" '[ -n "$ASSET" ] && [ "$(code "$ASSET")" = 200 ]'
check "frontend bundle does not point at a development origin" '! body "$ASSET" | grep -q "127.0.0.1:8000"'
check "offline snapshot index is served under /app/" '[ "$(code /app/snapshots/index.json)" = 200 ]'
check "/api/v2/status works" '[ "$(code /api/v2/status)" = 200 ]'
check "status reports missing project without secrets" 'body /api/v2/status | grep -q "EE_PROJECT_ID is not set"'
check "status reports direct-peer client identification" 'body /api/v2/status | grep -q "direct_peer_only"'
check "variables catalog works" 'body /api/v2/variables | grep -q "\"temperature\""'
check "API docs reachable (existing policy)" '[ "$(code /docs)" = 200 ] && [ "$(code /openapi.json)" = 200 ]'
check "Earth Engine readiness fails safely (503, no crash)" '[ "$(code /health 90)" = 503 ]'
check "Earth Engine variable fails with a clear error, not a crash" \
  'c=$(code "/api/v2/analysis?variable=ndvi&latitude=16.8661&longitude=96.1951&start_date=2015-01-01&end_date=2025-01-01" 90); [ "$c" = 503 ] || [ "$c" = 502 ]'
check "server still healthy after failures" '[ "$(code /)" = 200 ]'
check "spoofed X-Forwarded-For is not trusted by default" \
  '[ "$(code_with_header /api/v2/status "X-Forwarded-For: 203.0.113.9")" = 200 ] && body /api/v2/status | grep -q "direct_peer_only"'
check "no secrets or paths in error responses" '! body /health 90 | grep -qiE "private_key|BEGIN|/home/|\.json"'

echo "== Conflicting Earth Engine credential configuration"
start -e EE_PROJECT_ID=example-project -e EE_USE_APPLICATION_DEFAULT_CREDENTIALS=true -e EE_SERVICE_ACCOUNT_KEY_FILE=/nonexistent/key.json
check "status reports the conflict" 'body /api/v2/status | grep -q "conflicting_configuration"'
check "Earth Engine refuses to start (503)" '[ "$(code /health 90)" = 503 ]'

echo "== Keyless mode without a metadata server (not a hosted verification)"
start -e EE_PROJECT_ID=example-project -e EE_USE_APPLICATION_DEFAULT_CREDENTIALS=true
check "status reports application_default_credentials, not verified" \
  'body /api/v2/status | grep -q "\"auth_mode\":\"application_default_credentials\"" && body /api/v2/status | grep -q "\"credentials_verified\":false"'
check "missing ADC fails safely (503)" '[ "$(code /health 120)" = 503 ]'

echo "== Rate limiting with spoofed headers"
start -e EE_PROJECT_ID= -e RATE_LIMIT_PER_MINUTE=3
codes=""
for i in 1 2 3 4; do codes="$codes $(code_with_header /api/v2/variables "X-Forwarded-For: 203.0.113.$i")"; done
check "rotating X-Forwarded-For cannot bypass the limit ($codes)" '[ "$codes" = " 200 200 200 429" ]'

stop
echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES check(s) failed"; exit 1; fi
echo "All container smoke checks passed."
