#!/usr/bin/env bash
# verify.sh — end-to-end Dockerfile validation
#
# Run this BEFORE submitting to docker/mcp-registry to catch:
# - build errors (syntax, missing deps)
# - runtime errors (server doesn't start, healthcheck fails)
# - MCP protocol errors (server doesn't expose tools at /mcp)
# - image bloat (unused build deps not stripped)
#
# Usage:
#   ./verify.sh                # build local image and test
#   ./verify.sh --pull         # pull from GHCR and test (skip build)
#   ./verify.sh --image NAME   # custom image name
set -euo pipefail

IMAGE="${IMAGE:-mcp-aemps:verify}"
PULL=0
NAME="mcp-aemps-verify-$$"

# Pick a free TCP port between 18765-18999 to avoid colliding with the
# user's normal mcp-aemps server on 8765 or other dev servers.
find_free_port() {
  for p in $(seq 18765 18999); do
    if ! (echo > "/dev/tcp/127.0.0.1/$p") >/dev/null 2>&1; then
      echo "$p"; return
    fi
  done
  echo "Could not find a free port in 18765-18999" >&2; exit 1
}
PORT=$(find_free_port)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull) PULL=1; IMAGE="ghcr.io/romanpert/mcp-aemps:latest"; shift ;;
    --image) IMAGE="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

# ---- Cleanup on exit -------------------------------------------------------
cleanup() {
  echo ""
  echo "🧹 Cleaning up…"
  docker stop "$NAME" >/dev/null 2>&1 || true
  docker rm   "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

step() { echo ""; echo "━━━ $1 ━━━"; }
ok()   { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; exit 1; }

# ---- 1. Build (or pull) ----------------------------------------------------
if [[ $PULL -eq 1 ]]; then
  step "1. Pull image from GHCR"
  docker pull "$IMAGE"
  ok "pulled $IMAGE"
else
  step "1. Build image from local Dockerfile"
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  docker build -t "$IMAGE" "$REPO_ROOT"
  ok "built $IMAGE"
fi

# ---- 2. Inspect image metadata --------------------------------------------
step "2. Inspect image metadata (OCI labels, size, user)"
SIZE_MB=$(docker image inspect "$IMAGE" --format '{{.Size}}' | awk '{printf "%.0f", $1/1024/1024}')
USER=$(docker image inspect "$IMAGE" --format '{{.Config.User}}')
LABELS=$(docker image inspect "$IMAGE" --format '{{json .Config.Labels}}')

echo "  Size:   ${SIZE_MB} MB"
echo "  User:   ${USER:-root}"
echo "  Labels: $(echo "$LABELS" | PYTHONIOENCODING=utf-8 python -c "import sys,json; d=json.load(sys.stdin) or {}; [print(f'    {k}={v}') for k,v in d.items()]")"

[[ -n "$USER" && "$USER" != "root" && "$USER" != "0" ]] && ok "non-root user (${USER})" || fail "image runs as root!"
[[ "$SIZE_MB" -lt 250 ]] && ok "image size reasonable (${SIZE_MB} MB < 250 MB)" || echo "  ⚠️  image is ${SIZE_MB} MB — consider slimming"

# ---- 3. Run + wait for healthcheck ----------------------------------------
step "3. Run container + wait for healthcheck"
# Pass PORT to the container so it binds to the SAME port we map externally;
# this avoids the foot-gun of mapping host:X -> container:8765 (the image
# default) when X != 8765.
docker run -d --rm --name "$NAME" -e PORT="$PORT" -p "${PORT}:${PORT}" "$IMAGE" >/dev/null
ok "container started ($NAME) on port $PORT"

# Poll /health for up to 30 seconds
echo -n "  Waiting for /health "
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo " ready"
    break
  fi
  echo -n "."
  sleep 1
  if [[ $i -eq 30 ]]; then
    echo ""
    echo "  --- container logs ---"
    docker logs "$NAME" 2>&1 | tail -30
    fail "/health never responded"
  fi
done

# ---- 4. /health response ---------------------------------------------------
step "4. Validate /health response"
HEALTH=$(curl -s "http://localhost:${PORT}/health")
echo "  $HEALTH"

echo "$HEALTH" | PYTHONIOENCODING=utf-8 python -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'ok', f'status={d[\"status\"]}'
assert 'version' in d, 'missing version'
assert d['cache'] in ('in-memory', 'redis'), f'unexpected cache={d[\"cache\"]}'
print(f'  [OK] status=ok, version={d[\"version\"]}, cache={d[\"cache\"]}')
" || fail "/health response invalid"

# ---- 5. /openapi.json — endpoints exposed ----------------------------------
step "5. Validate OpenAPI surface (CIMA endpoints exposed)"
ENDPOINTS=$(curl -s "http://localhost:${PORT}/openapi.json" | PYTHONIOENCODING=utf-8 python -c "
import sys, json
d = json.load(sys.stdin)
paths = list(d.get('paths', {}).keys())
print(len(paths))
for p in sorted(paths):
    print(p)
")
N_ENDPOINTS=$(echo "$ENDPOINTS" | head -1)
echo "  Endpoints: $N_ENDPOINTS"
echo "$ENDPOINTS" | tail -n +2 | sed 's/^/    /'
[[ "$N_ENDPOINTS" -ge 18 ]] && ok "$N_ENDPOINTS endpoints (>= 18 expected)" || fail "only $N_ENDPOINTS endpoints"

# ---- 6. /mcp — MCP protocol probe -----------------------------------------
step "6. Probe /mcp (MCP streamable-http endpoint reachable)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:${PORT}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"0"}}}' \
  || echo "ERR")
# 200 = direct response, 202 = accepted (background), both fine. 404/500 = bad.
if [[ "$HTTP_CODE" =~ ^(200|202)$ ]]; then
  ok "/mcp responded $HTTP_CODE to initialize"
else
  fail "/mcp returned $HTTP_CODE (expected 200 or 202)"
fi

# ---- 7. /internal/metrics --------------------------------------------------
step "7. Validate /internal/metrics counters"
METRICS=$(curl -s "http://localhost:${PORT}/internal/metrics")
echo "$METRICS" | PYTHONIOENCODING=utf-8 python -c "
import sys, json
d = json.load(sys.stdin)
required = {'version', 'uptime_seconds', 'requests_total', 'requests_by_path', 'status_codes'}
missing = required - set(d)
assert not missing, f'missing keys: {missing}'
assert d['requests_total'] > 0, 'no requests recorded'
print(f'  [OK] requests_total={d[\"requests_total\"]}, uptime={d[\"uptime_seconds\"]}s')
" || fail "/internal/metrics invalid"

# ---- 8. Container is still healthy after the test --------------------------
step "8. Container final state"
STATE=$(docker inspect "$NAME" --format '{{.State.Status}}')
HEALTH_STATE=$(docker inspect "$NAME" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' 2>/dev/null || echo "-")
echo "  state=$STATE  health=$HEALTH_STATE"
[[ "$STATE" == "running" ]] && ok "container still running" || fail "container exited"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Dockerfile validation PASSED — image is ready for Docker MCP Registry"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
