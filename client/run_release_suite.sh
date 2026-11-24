#!/usr/bin/env bash
#
# Run the release test scripts one after another and report an overall result.
#
# Each script under ui/gui/tests runs with the GUI venv's Python. The direct and examples
# tests run as is with HOST_SERVER_URL set; the others run under xvfb-run with the GUI base
# URL as their argument. Warnings the tests append to RELEASE_WARN_FILE are summarised at the end.
#
# USAGE:
#   ./run_release_suite.sh [base_url]
#
# DEPENDENCIES:
#   - ui/gui/.venv/bin/python3 (created by setup.sh)
#   - xvfb-run (headless display for browser tests)
#   - docker (optional; to read the API key from a container)
#   - mktemp, awk, wc
#
# ARGUMENTS:
#   $1 (string): Base URL of the running GUI. Defaults to http://127.0.0.1:8080.
#
# ENV VARIABLES:
#   HOST_SERVER_URL (string): Host server URL. Required: No. Default: the base URL with its port
#     replaced by 8088.
#   HOST_SERVER_API_KEY (string): Host server API key. Required: No. Default: read from
#     $WORKDIR/deployment/.env inside container $CONTAINER when both are set and docker exists.
#   CONTAINER (string): Docker container to read the API key from. Required: No.
#   WORKDIR (path): Directory inside CONTAINER holding deployment/.env. Required: No.
#   AXMONITOR_TRACE (string): Exported to the tests. Required: No. Default: 1.
#   AXMONITOR_HOST_SERVER_URL (string): Exported to the tests. Required: No. Default: HOST_SERVER_URL or the derived URL.
#   AXMONITOR_API_KEY (string): Exported to the tests. Required: No. Default: HOST_SERVER_API_KEY.
#
# EXIT CODES:
#   0: Every test script exited with 0.
#   1: At least one test script failed.
#
# EXAMPLE:
#   ./run_release_suite.sh http://127.0.0.1:8080
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

BASE_URL="${1:-http://127.0.0.1:8080}"

if [[ "$BASE_URL" =~ ^(.*):[0-9]+$ ]]; then
  HOST_SERVER_URL_DEFAULT="${BASH_REMATCH[1]}:8088"
else
  HOST_SERVER_URL_DEFAULT="${BASE_URL}:8088"
fi

export AXMONITOR_TRACE="${AXMONITOR_TRACE:-1}"
export AXMONITOR_HOST_SERVER_URL="${AXMONITOR_HOST_SERVER_URL:-${HOST_SERVER_URL:-$HOST_SERVER_URL_DEFAULT}}"
if [ -z "${HOST_SERVER_API_KEY:-}" ] && [ -n "${CONTAINER:-}" ] && [ -n "${WORKDIR:-}" ] \
    && command -v docker >/dev/null 2>&1; then
  HOST_SERVER_API_KEY="$(docker exec "$CONTAINER" bash -c "grep '^DEPLOYMENT_API_KEY=' $WORKDIR/deployment/.env | cut -d= -f2-" 2>/dev/null || true)"
  export HOST_SERVER_API_KEY
fi
if [ -z "${AXMONITOR_API_KEY:-}" ] && [ -n "${HOST_SERVER_API_KEY:-}" ]; then
  export AXMONITOR_API_KEY="$HOST_SERVER_API_KEY"
fi

TESTS=(
  ui/gui/tests/test_release_playwright_isovision.py
  ui/gui/tests/test_release_fastapi_isovision.py
  ui/gui/tests/test_release_playwright_cascade.py
  ui/gui/tests/test_release_fastapi_cascade.py
  ui/gui/tests/test_release_playwright_cascade3.py
  ui/gui/tests/test_release_fastapi_cascade3.py
  ui/gui/tests/test_release_playwright_cascade3_e2e_user_workflow.py
  ui/gui/tests/test_release_fastapi_cascade3_e2e_user_workflow.py
  ui/gui/tests/test_release_playwright_vlm.py
  ui/gui/tests/test_release_fastapi_vlm.py
  ui/gui/tests/test_release_direct_vlm.py
  ui/gui/tests/test_release_playwright_llm.py
  ui/gui/tests/test_release_fastapi_llm.py
  ui/gui/tests/test_release_direct_llm.py
  ui/gui/tests/test_release_examples_helper.py
  ui/gui/tests/test_release_examples_vision.py
  ui/gui/tests/test_release_examples_cascade.py
  ui/gui/tests/test_release_examples_cascade3.py
  ui/gui/tests/test_release_examples_vlm.py
  ui/gui/tests/test_release_examples_llm.py
)
RELEASE_WARN_FILE="$(mktemp)"
export RELEASE_WARN_FILE
trap 'rm -f "$RELEASE_WARN_FILE"' EXIT
OVERALL=0
for t in "${TESTS[@]}"; do
  echo "=============================================="
  echo "RUNNING: $t"
  echo "=============================================="
  export RELEASE_TEST_NAME="$t"
  case "$t" in
  */test_release_direct_*.py|*/test_release_examples_*.py)
    HOST_SERVER_URL="${HOST_SERVER_URL:-$HOST_SERVER_URL_DEFAULT}" ui/gui/.venv/bin/python3 "$t"
    ;;
  *)
    xvfb-run -a ui/gui/.venv/bin/python3 "$t" "$BASE_URL"
    ;;
  esac
  rc=$?
  echo "EXIT CODE for $t: $rc"
  if [ "$rc" -ne 0 ]; then OVERALL=1; fi
done
echo "=============================================="
WARNINGS=$(wc -l < "$RELEASE_WARN_FILE")
if [ "$WARNINGS" -gt 0 ]; then
  echo "WARNINGS ($WARNINGS):"
  awk -F'\t' '{printf "  %s: %s\n", $1, $2}' "$RELEASE_WARN_FILE"
fi
echo "OVERALL RESULT: $([ $OVERALL -eq 0 ] && echo ALL_PASS || echo SOME_FAILED)$([ "$WARNINGS" -gt 0 ] && echo " ($WARNINGS warning(s))")"
echo "=============================================="
exit $OVERALL
