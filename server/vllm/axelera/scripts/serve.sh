#!/usr/bin/env bash
#
# Serve a compiled Axelera model with the vLLM OpenAI-compatible API server.
#
# Checks that the Axelera runtime imports, asks axplugin.hf_adapter for
# --hf-overrides for the model, then execs vllm.entrypoints.openai.api_server in
# eager mode with the Axelera device and temperature passed via --additional-config.
# Extra arguments are forwarded to the server.
#
# USAGE:
#   MODEL=<artifact_dir> ./serve.sh [extra vllm args...]
#
# DEPENDENCIES:
#   - python with vllm and axelera.runtime (AXELERA_PYTHON, else <pkg>/.venv/bin/python, else python3)
#
# ENV VARIABLES:
#   MODEL (path): Compiled artifact directory (not a HF Hub id). Required: Yes.
#   AXELERA_PYTHON (path): Python interpreter. Required: No. Default: <pkg>/.venv/bin/python, falling back to python3.
#   PORT (int): Server port. Required: No. Default: 8000.
#   DEVICE (string): Metis device id. Required: No. Default: metis-0:23:0.
#   THINKING (string): "off" disables chat-template thinking; any other value leaves it on. Required: No. Default: off.
#   TEMPERATURE (float): Value for additional-config temperature. Required: No. Default: 0.0.
#
# EXIT CODES:
#   0: Not returned normally; the script execs the server.
#   1: MODEL is not a directory, or the runtime import check failed.
#   non-zero: MODEL unset (bash parameter check) or other command failure (set -e).
#
# EXAMPLE:
#   MODEL=$SDK_DIR/build/qwen3-0.6b/axscript PORT=8010 ./serve.sh
set -euo pipefail

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${AXELERA_PYTHON:-$PKG/.venv/bin/python}"
[[ -x "$PYTHON" ]] || PYTHON=python3

: "${MODEL:?Set MODEL to a compiled artifact directory, e.g. \$SDK_DIR/build/qwen3-0.6b/axscript}"
[[ -d "$MODEL" ]] || { echo "ERROR: MODEL '$MODEL' is not a directory (resolve_artifact_dir expects an artifact_dir, not a HF Hub repo id)" >&2; exit 1; }

PORT="${PORT:-8000}"
DEVICE="${DEVICE:-metis-0:23:0}"
THINKING="${THINKING:-off}"
TEMPERATURE="${TEMPERATURE:-0.0}"

export HF_HUB_OFFLINE=1
unset SETUPTOOLS_USE_DISTUTILS

"$PYTHON" -c 'import axelera.runtime.axruntime as a, axelera.runtime.axddr as d
print("libaxruntime:", a.LIBRARY_PATH); print("stage0:    ", d.stage0_path())' || exit 1

HF_OVERRIDES="$("$PYTHON" -c '
import json, sys
from axplugin import hf_adapter
print(json.dumps(hf_adapter.hf_overrides_for(sys.argv[1])))
' "$MODEL")"

EXTRA=()
[[ "$THINKING" == "off" ]] && EXTRA+=(--default-chat-template-kwargs '{"enable_thinking": false}')
[[ "$HF_OVERRIDES" != "{}" ]] && EXTRA+=(--hf-overrides "$HF_OVERRIDES")

cd "$PKG"
echo "serving $MODEL on http://127.0.0.1:$PORT (device $DEVICE, thinking $THINKING)" >&2
exec "$PYTHON" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --port "$PORT" \
    --enforce-eager \
    --additional-config "{\"device\": \"$DEVICE\", \"temperature\": $TEMPERATURE}" \
    "${EXTRA[@]}" \
    "$@"
