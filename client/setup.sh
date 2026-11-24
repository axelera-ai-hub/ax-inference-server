#!/bin/bash
#
# Set up the client GUI environment, and optionally the agent CLI, debug tooling, tracker
# libraries, or restart the GUI app.
#
# USAGE:
#   ./setup.sh [--agent] [--debug] [--tracker]
#   HOST_SERVER_URL=... HOST_SERVER_API_KEY=... ./setup.sh --restart
#
# PHASES (in order; the first four are skipped by --restart):
#   clone_nicegui         Clone NiceGUI at a pinned tag and check it is at the pinned commit.
#   build_vue_flow_bundle Install Node 24 via nvm if npm is missing, then build ui/gui/components.
#   gui_venv_setup        Create ui/gui/.venv and install the Python dependencies.
#   gen_grpc_stubs        Run inference/gen_stubs.sh with the venv on PATH.
#   agent_cli             (--agent) Run docs/helper/agent/setup.sh.
#   debug_tooling         (--debug) Install Playwright with Chromium and xvfb.
#   tracker_bringup       (--tracker) Clone pinned roboflow trackers and supervision into
#                         tracker/roboflow and install them into the GUI venv.
#   restart_gui           (--restart) Stop any running app.py in ui/gui and start a new one.
#
# DEPENDENCIES:
#   - git, curl (cloning; nvm installer)
#   - python3 with the venv module (GUI venv)
#   - npm / Node (installed through nvm when npm is absent)
#   - sudo, apt-get (--debug: browser dependencies and xvfb)
#   - pgrep, nohup (--restart)
#
# ARGUMENTS:
#   --agent (flag): Also run the agent CLI setup.
#   --restart (flag): Skip environment setup and (re)start the GUI app.
#   --debug (flag): Also install Playwright and xvfb. Requires an existing GUI venv.
#   --tracker (flag): Also install the tracker libraries. Requires an existing GUI venv.
#
# ENV VARIABLES:
#   HOST_SERVER_URL (string): Host server URL passed to app.py. Required: Yes with --restart.
#   HOST_SERVER_API_KEY (string): API key passed to app.py. Required: Yes with --restart.
#   GUI_APP_PORT (int): Port for app.py. Required: No. Default: 8080.
#   NVM_DIR (path): nvm installation directory. Required: No. Default: $HOME/.nvm.
#
# EXIT CODES:
#   0: Success.
#   1: Unknown argument, pinned-commit mismatch, missing build output, missing GUI venv for
#      --debug/--tracker, missing --restart variables, or app.py exited at startup.
#   other: A failing command under set -e.
#
# EXAMPLE:
#   ./setup.sh --debug --tracker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR"

WITH_AGENT=0
RESTART=0
DEBUG=0
TRACKER=0
for arg in "$@"; do
  case "$arg" in
    --agent) WITH_AGENT=1 ;;
    --restart) RESTART=1 ;;
    --debug) DEBUG=1 ;;
    --tracker) TRACKER=1 ;;
    *) echo "ERROR: unknown argument: $arg" >&2; exit 1 ;;
  esac
done

# Print a message prefixed with the script name.
#
# Arguments:
#   $@ (string): Message text.
#
# Outputs:
#   stdout: "[client/setup.sh] <message>".
#
# Returns:
#   0: Success.
log() { echo "[client/setup.sh] $*"; }

NICEGUI_DIR="$CLIENT_DIR/ui/nice-gui"
GUI_DIR="$CLIENT_DIR/ui/gui"
VENV_DIR="$GUI_DIR/.venv"
PINNED_TAG=v3.18.0
PINNED_COMMIT=2449c4a4be064d364e4a0f838ad6d8bc6d9aad69
PLAYWRIGHT_VERSION=1.62.0
TRACKERS_PINNED_COMMIT=c25b23472acc71bea37d2e5849199e06a225e9c0
SUPERVISION_PINNED_COMMIT=a32a9e828cad934bcb798a13250f96d0cb7b4e84

if [[ "$RESTART" -eq 1 ]]; then
  log "PHASE: environment_setup SKIP (--restart passed, assuming already set up)"
else

if [[ -d "$NICEGUI_DIR/.git" ]]; then
  log "PHASE: clone_nicegui SKIP (already present at $NICEGUI_DIR)"
else
  log "PHASE: clone_nicegui (cloning $PINNED_TAG)"
  git clone --branch "$PINNED_TAG" --depth 1 https://github.com/zauberzeug/nicegui.git "$NICEGUI_DIR"
fi
ACTUAL_COMMIT=$(git -C "$NICEGUI_DIR" rev-parse HEAD)
if [[ "$ACTUAL_COMMIT" != "$PINNED_COMMIT" ]]; then
  echo "ERROR: nice-gui at $ACTUAL_COMMIT, expected pinned $PINNED_COMMIT" >&2
  exit 1
fi
log "PHASE: clone_nicegui PASS (pinned at $PINNED_COMMIT)"

COMPONENTS_DIR="$CLIENT_DIR/ui/gui/components"
if ! command -v npm >/dev/null 2>&1; then
  log "PHASE: build_vue_flow_bundle (npm not found, installing Node 24 via nvm)"
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm install 24
fi
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  . "$NVM_DIR/nvm.sh"
fi

log "PHASE: build_vue_flow_bundle (npm install + build)"
(
  cd "$COMPONENTS_DIR"
  npm install --no-audit --no-fund
  npm run build
)
if [[ ! -f "$COMPONENTS_DIR/dist/index.js" ]]; then
  echo "ERROR: build did not produce $COMPONENTS_DIR/dist/index.js" >&2
  exit 1
fi
log "PHASE: build_vue_flow_bundle PASS"

if [[ -x "$VENV_DIR/bin/python3" ]]; then
  log "PHASE: gui_venv_setup (venv already at $VENV_DIR)"
else
  log "PHASE: gui_venv_setup (creating $VENV_DIR)"
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -e "$NICEGUI_DIR"
"$VENV_DIR/bin/pip" install -q pyyaml pydantic psutil
"$VENV_DIR/bin/pip" install -q numpy==1.26.4 opencv-python==4.11.0.86
"$VENV_DIR/bin/pip" install -q imageio-ffmpeg==0.8.1
"$VENV_DIR/bin/pip" install -q grpcio grpcio-tools
"$VENV_DIR/bin/pip" install -q fastmcp==4.1.4 mcp==2.3.0
log "PHASE: gui_venv_setup PASS"

log "PHASE: gen_grpc_stubs"
PATH="$VENV_DIR/bin:$PATH" bash "$CLIENT_DIR/inference/gen_stubs.sh"
log "PHASE: gen_grpc_stubs PASS"

"$VENV_DIR/bin/python3" -c "import nicegui, numpy, cv2, fastmcp; print('deps OK')"
log "client/setup.sh: ALL PHASES PASS"

fi

if [[ "$WITH_AGENT" -eq 1 ]]; then
  log "PHASE: agent_cli (--agent passed)"
  bash "$CLIENT_DIR/docs/helper/agent/setup.sh"
  log "PHASE: agent_cli PASS"
fi

if [[ "$DEBUG" -eq 1 ]]; then
  log "PHASE: debug_tooling (--debug passed)"
  if [[ ! -x "$VENV_DIR/bin/pip" ]]; then
    echo "ERROR: --debug requires the GUI venv at $VENV_DIR -- run setup.sh without --restart first" >&2
    exit 1
  fi

  "$VENV_DIR/bin/pip" install -q "playwright==$PLAYWRIGHT_VERSION"
  "$VENV_DIR/bin/python" -m playwright install chromium
  sudo "$VENV_DIR/bin/python" -m playwright install-deps chromium

  if command -v xvfb-run >/dev/null 2>&1; then
    log "xvfb already installed, skipping apt-get"
  else
    log "installing xvfb"
    sudo apt-get update -qq
    sudo apt-get install -y xvfb
  fi
  log "PHASE: debug_tooling PASS"
fi

if [[ "$TRACKER" -eq 1 ]]; then
  log "PHASE: tracker_bringup (--tracker passed)"
  if [[ ! -x "$VENV_DIR/bin/pip" ]]; then
    echo "ERROR: --tracker requires the GUI venv at $VENV_DIR -- run setup.sh without --restart first" >&2
    exit 1
  fi
  TRACKER_DIR="$CLIENT_DIR/tracker"
  ROBOFLOW_DIR="$TRACKER_DIR/roboflow"
  TRACKERS_SRC="$ROBOFLOW_DIR/trackers"
  SUPERVISION_SRC="$ROBOFLOW_DIR/supervision"

  mkdir -p "$ROBOFLOW_DIR"

  if [[ -d "$TRACKERS_SRC/.git" ]]; then
    CUR="$(git -C "$TRACKERS_SRC" rev-parse HEAD)"
    if [[ "$CUR" != "$TRACKERS_PINNED_COMMIT" ]]; then
      echo "ERROR: $TRACKERS_SRC exists but HEAD=$CUR != pinned $TRACKERS_PINNED_COMMIT -- refusing to overwrite" >&2
      exit 1
    fi
    log "roboflow/trackers already at pinned commit, skipping clone"
  else
    git clone https://github.com/roboflow/trackers.git "$TRACKERS_SRC"
    git -C "$TRACKERS_SRC" checkout "$TRACKERS_PINNED_COMMIT"
    CUR="$(git -C "$TRACKERS_SRC" rev-parse HEAD)"
    [[ "$CUR" == "$TRACKERS_PINNED_COMMIT" ]] || { echo "ERROR: trackers checkout landed on $CUR, not $TRACKERS_PINNED_COMMIT" >&2; exit 1; }
  fi

  if [[ -d "$SUPERVISION_SRC/.git" ]]; then
    CUR="$(git -C "$SUPERVISION_SRC" rev-parse HEAD)"
    if [[ "$CUR" != "$SUPERVISION_PINNED_COMMIT" ]]; then
      echo "ERROR: $SUPERVISION_SRC exists but HEAD=$CUR != pinned $SUPERVISION_PINNED_COMMIT -- refusing to overwrite" >&2
      exit 1
    fi
    log "roboflow/supervision already at pinned commit, skipping clone"
  else
    git clone --depth 1 -b develop https://github.com/roboflow/supervision.git "$SUPERVISION_SRC"
    CUR="$(git -C "$SUPERVISION_SRC" rev-parse HEAD)"
    if [[ "$CUR" != "$SUPERVISION_PINNED_COMMIT" ]]; then
      git -C "$SUPERVISION_SRC" fetch --unshallow origin
      git -C "$SUPERVISION_SRC" checkout "$SUPERVISION_PINNED_COMMIT"
      CUR="$(git -C "$SUPERVISION_SRC" rev-parse HEAD)"
      [[ "$CUR" == "$SUPERVISION_PINNED_COMMIT" ]] || { echo "ERROR: could not reach pinned supervision commit $SUPERVISION_PINNED_COMMIT (at $CUR)" >&2; exit 1; }
    fi
  fi

  if "$VENV_DIR/bin/python3" -c "import trackers, supervision" 2>/dev/null; then
    log "GUI venv already has trackers/supervision, skipping pip install"
  else
    "$VENV_DIR/bin/pip" install -q -e "$SUPERVISION_SRC"
    "$VENV_DIR/bin/pip" install -q -e "$TRACKERS_SRC"
  fi
  "$VENV_DIR/bin/python3" -c "
import supervision, trackers
assert 'roboflow/supervision' in supervision.__file__, supervision.__file__
assert 'roboflow/trackers' in trackers.__file__, trackers.__file__
"
  log "PHASE: tracker_bringup PASS ($VENV_DIR, trackers@$TRACKERS_PINNED_COMMIT, supervision@$SUPERVISION_PINNED_COMMIT)"
fi

if [[ "$RESTART" -eq 1 ]]; then
  log "PHASE: restart_gui (--restart passed)"
  : "${HOST_SERVER_URL:?--restart requires HOST_SERVER_URL to be exported -- see client/quickstart.md's launch step}"
  : "${HOST_SERVER_API_KEY:?--restart requires HOST_SERVER_API_KEY to be exported -- see client/quickstart.md's launch step}"

  OLD_PIDS=()
  for p in $(pgrep -f '(^|/)python[0-9.]* app\.py$' || true); do
    if [[ "$(readlink -f "/proc/$p/cwd" 2>/dev/null)" == "$(readlink -f "$GUI_DIR")" ]]; then
      OLD_PIDS+=("$p")
    fi
  done
  if [[ ${#OLD_PIDS[@]} -gt 0 ]]; then
    for OLD_PID in "${OLD_PIDS[@]}"; do
      log "stopping existing app.py (pid $OLD_PID)"
      python3 -c "
import os, sys, time
pid = $OLD_PID
os.kill(pid, 15)
for _ in range(100):
    try:
        os.kill(pid, 0)
    except OSError:
        sys.exit(0)
    time.sleep(0.1)
sys.exit(f'timed out waiting for pid {pid} to exit')
"
    done
  else
    log "no running app.py found, nothing to stop"
  fi

  GUI_APP_PORT="${GUI_APP_PORT:-8080}"
  log "launching app.py (HOST_SERVER_URL=$HOST_SERVER_URL, port $GUI_APP_PORT)"
  cd "$GUI_DIR"
  HOST_SERVER_URL="$HOST_SERVER_URL" \
  HOST_SERVER_API_KEY="$HOST_SERVER_API_KEY" \
  GUI_APP_PORT="$GUI_APP_PORT" \
  nohup "$VENV_DIR/bin/python" app.py > .gui_live.log 2>&1 < /dev/null &
  NEW_PID=$!
  sleep 3
  if ! kill -0 "$NEW_PID" 2>/dev/null; then
    log "PHASE: restart_gui FAIL (app.py exited at startup; see $GUI_DIR/.gui_live.log)"
    exit 1
  fi
  log "PHASE: restart_gui PASS (pid $NEW_PID; see $GUI_DIR/.gui_live.log)"
fi
