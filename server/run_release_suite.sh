#!/usr/bin/env bash
#
# Run the release test files against a host server and report an overall result.
#
# Runs each file in TESTS with ../.venv-vllm/bin/python3, passing the base URL as
# its argument, then prints per-file exit codes and ALL_PASS or SOME_FAILED.
#
# USAGE:
#   ./run_release_suite.sh [base_url]
#
# ARGUMENTS:
#   $1 (url): Host server base URL. Defaults to $HOST_SERVER_URL (empty if unset).
#
# ENV VARIABLES:
#   HOST_SERVER_URL (url): Fallback base URL. Required: No.
#
# EXIT CODES:
#   0: All test files passed.
#   1: At least one test file failed.
#
# EXAMPLE:
#   ./run_release_suite.sh http://localhost:8080
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

BASE_URL="${1:-${HOST_SERVER_URL:-}}"
PYTHON="../.venv-vllm/bin/python3"

TESTS=(
  tests/test_release_host_server.py
)
OVERALL=0
for t in "${TESTS[@]}"; do
  echo "=============================================="
  echo "RUNNING: $t"
  echo "=============================================="
  "$PYTHON" "$t" "$BASE_URL"
  rc=$?
  echo "EXIT CODE for $t: $rc"
  if [ "$rc" -ne 0 ]; then OVERALL=1; fi
done
echo "=============================================="
echo "OVERALL RESULT: $([ $OVERALL -eq 0 ] && echo ALL_PASS || echo SOME_FAILED)"
echo "=============================================="
exit $OVERALL
