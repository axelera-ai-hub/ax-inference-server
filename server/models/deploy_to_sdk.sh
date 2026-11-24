#!/bin/bash
#
# Deploy compiled model axscript directories into a voyager-sdk build tree.
#
# Copies <script dir>/<model>/axscript to <sdk-dir>/build/<model>/axscript for
# each selected model. A model already present at the destination is skipped
# unless --force is given.
#
# USAGE:
#   ./deploy_to_sdk.sh --sdk-dir PATH [--model NAME [--model NAME ...]] [--force]
#
# DEPENDENCIES:
#   - find, cp, rm, mkdir (discovering and copying model directories)
#
# ARGUMENTS:
#   --sdk-dir PATH (path): voyager-sdk checkout. Required; must already exist.
#   --model NAME (string): Deploy only this model; may be repeated. Defaults to
#       every subdirectory next to this script that contains an axscript/ dir.
#   --force (flag): Overwrite an existing destination. Default: skip it.
#   -h, --help: Print usage and exit.
#
# EXIT CODES:
#   0: Success (including --help).
#   1: --sdk-dir does not exist, no model found, or a model has no axscript/ dir.
#   2: Unknown argument or missing --sdk-dir.
#
# EXAMPLE:
#   ./deploy_to_sdk.sh --sdk-dir .sdk/voyager-sdk --model qwen3-0.6b --force
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Print the usage text.
#
# Outputs:
#   stdout: Usage and option descriptions (callers redirect to stderr on errors).
usage() {
  cat <<'EOF'
Usage: deploy_to_sdk.sh --sdk-dir PATH [--model NAME [--model NAME ...]] [--force]

  --sdk-dir PATH   Path to a voyager-sdk checkout (must already exist, e.g.
                    .sdk/voyager-sdk). Models are copied into
                    <PATH>/build/<model-name>/axscript/.
  --model NAME      Deploy only this model (may be repeated). NAME must be a
                    subdirectory of server/models/ containing an axscript/
                    dir. Default: every such subdirectory.
  --force           Overwrite an existing <sdk-dir>/build/<model-name>/axscript/
                    if present. Default: skip (reuse) if already present.
EOF
}

SDK_DIR=""
FORCE=0
MODELS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sdk-dir) SDK_DIR="$2"; shift 2 ;;
    --model) MODELS+=("$2"); shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$SDK_DIR" ]]; then
  echo "ERROR: --sdk-dir is required" >&2
  exit 2
fi
if [[ ! -d "$SDK_DIR" ]]; then
  echo "ERROR: --sdk-dir does not exist: $SDK_DIR" >&2
  exit 1
fi

# Print a message prefixed with the script name.
#
# Arguments:
#   $*: Message text.
#
# Outputs:
#   stdout: "[deploy_to_sdk.sh] <message>".
log() { echo "[deploy_to_sdk.sh] $*"; }

if [[ ${#MODELS[@]} -eq 0 ]]; then
  while IFS= read -r -d '' axscript_dir; do
    MODELS+=("$(basename "$(dirname "$axscript_dir")")")
  done < <(find "$SCRIPT_DIR" -mindepth 2 -maxdepth 2 -type d -name axscript -print0)
fi

if [[ ${#MODELS[@]} -eq 0 ]]; then
  echo "ERROR: no model found under $SCRIPT_DIR with an axscript/ subdirectory" >&2
  exit 1
fi

BUILD_DIR="$SDK_DIR/build"
mkdir -p "$BUILD_DIR"

for model in "${MODELS[@]}"; do
  SRC="$SCRIPT_DIR/$model/axscript"
  DEST="$BUILD_DIR/$model/axscript"
  if [[ ! -d "$SRC" ]]; then
    echo "ERROR: $SRC not found (is '$model' a valid model under server/models/?)" >&2
    exit 1
  fi
  if [[ -d "$DEST" && "$FORCE" != "1" ]]; then
    log "SKIP $model (already present at $DEST; use --force to overwrite)"
    continue
  fi
  log "deploying $model -> $DEST"
  rm -rf "$DEST"
  mkdir -p "$(dirname "$DEST")"
  cp -a "$SRC" "$DEST"
  log "PASS $model"
done

log "ALL MODELS DEPLOYED (sdk-dir=$SDK_DIR)"
