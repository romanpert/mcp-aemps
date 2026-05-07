#!/usr/bin/env bash
# MCP Inspector compliance smoke — boots the HTTP transport, runs
# `npx @modelcontextprotocol/inspector --cli` against the spec entry
# points and asserts protocol conformance.
#
# Catches regressions that unit tests don't surface: wrong content
# types, missing _meta blocks, capability advertisement drift, tools
# with empty titles or descriptions, etc.
#
# Invoked from .github/workflows/ci.yml; runnable locally too:
#
#   bash tests/inspector_compliance.sh
#
# Requirements: bash, curl, jq, python (with the package installed),
# Node.js >= 24 (npx). PORT and SERVER_URL are env-overridable.

set -euo pipefail

PORT="${PORT:-18765}"
SERVER_URL="${SERVER_URL:-http://127.0.0.1:${PORT}/mcp}"
HEALTH_URL="http://127.0.0.1:${PORT}/health/live"
INSPECTOR_PKG="@modelcontextprotocol/inspector"
LOG_FILE="$(mktemp)"
PID=""

cleanup() {
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
  fi
  if [[ -f "${LOG_FILE}" ]]; then
    echo "--- server log tail ---"
    tail -n 50 "${LOG_FILE}" || true
    rm -f "${LOG_FILE}"
  fi
}
trap cleanup EXIT

echo "▶ booting uvicorn on :${PORT}"
python -m uvicorn app.mcp_aemps_server:app \
  --host 127.0.0.1 --port "${PORT}" --log-level warning \
  > "${LOG_FILE}" 2>&1 &
PID=$!

echo "▶ waiting for ${HEALTH_URL}"
for i in $(seq 1 60); do
  if curl -sf "${HEALTH_URL}" > /dev/null; then
    echo "  up after ${i}s"
    break
  fi
  if ! kill -0 "${PID}" 2>/dev/null; then
    echo "✖ server died during startup"; exit 1
  fi
  sleep 1
done
curl -sf "${HEALTH_URL}" > /dev/null || { echo "✖ server never became healthy"; exit 1; }

inspect() {
  local method="$1"
  npx -y "${INSPECTOR_PKG}" --cli "${SERVER_URL}" --transport http --method "${method}"
}

echo "▶ tools/list"
TOOLS_JSON="$(inspect tools/list)"
TOOL_COUNT=$(echo "${TOOLS_JSON}" | jq '.tools | length')
[[ "${TOOL_COUNT}" -ge 21 ]] || { echo "✖ expected ≥21 tools, got ${TOOL_COUNT}"; echo "${TOOLS_JSON}"; exit 1; }
MISSING_TITLE=$(echo "${TOOLS_JSON}" | jq '[.tools[] | select(.title == null or .title == "") | .name]')
[[ "$(echo "${MISSING_TITLE}" | jq 'length')" -eq 0 ]] || { echo "✖ tools missing title: ${MISSING_TITLE}"; exit 1; }
MISSING_DESC=$(echo "${TOOLS_JSON}" | jq '[.tools[] | select(.description == null or .description == "") | .name]')
[[ "$(echo "${MISSING_DESC}" | jq 'length')" -eq 0 ]] || { echo "✖ tools missing description: ${MISSING_DESC}"; exit 1; }
MISSING_ANN=$(echo "${TOOLS_JSON}" | jq '[.tools[] | select(.annotations == null or .annotations.readOnlyHint != true) | .name]')
[[ "$(echo "${MISSING_ANN}" | jq 'length')" -eq 0 ]] || { echo "✖ tools missing readOnly annotation: ${MISSING_ANN}"; exit 1; }
echo "  ✓ ${TOOL_COUNT} tools, all with title + description + readOnly annotation"

echo "▶ prompts/list"
PROMPTS_JSON="$(inspect prompts/list)"
PROMPT_COUNT=$(echo "${PROMPTS_JSON}" | jq '.prompts | length')
[[ "${PROMPT_COUNT}" -ge 10 ]] || { echo "✖ expected ≥10 prompts, got ${PROMPT_COUNT}"; echo "${PROMPTS_JSON}"; exit 1; }
echo "  ✓ ${PROMPT_COUNT} prompts"

echo "▶ resources/list"
RES_JSON="$(inspect resources/list)"
RES_COUNT=$(echo "${RES_JSON}" | jq '.resources | length')
[[ "${RES_COUNT}" -ge 1 ]] || { echo "✖ expected ≥1 resource, got ${RES_COUNT}"; echo "${RES_JSON}"; exit 1; }
echo "  ✓ ${RES_COUNT} resources"

echo "✅ MCP Inspector compliance: PASS"
