#!/bin/bash
#
# Install and start AxMonitor (the axmonitor CLI and the axsystemserver daemon).
#
# AxMonitor comes from the apt package axelera-voyager-sdk-base-<SDK version>,
# which is separate from the pip-based SDK runtime install. Each phase is
# skipped when already satisfied, so the script can be re-run safely.
#
# USAGE:
#   SDK_ROOT=/path/to/voyager-sdk ./setup.sh
#
# PHASES:
#   resolve_version   Read the SDK version from $SDK_ROOT/venv/bin/axversion,
#                     else $SDK_ROOT/VERSION.TXT.
#   apt_repo          Add the Axelera apt source and keyring if missing
#                     (Ubuntu 22 or 24 only).
#   install_package   apt-get install the base package and libqt6svg6.
#   start_daemon      Start the axsystemserver service if not running.
#   activate_runtime  Source /opt/axelera/sdk/<version>/axelera_activate.sh if
#                     present (warns and continues if not).
#   smoke_test        Run axmonitor once against 127.0.0.1:5555; a failure is
#                     only a warning.
#
# DEPENDENCIES:
#   - apt-get, dpkg (package install)
#   - curl, gpg (fetch and install the apt signing key)
#   - service (start axsystemserver)
#   - sudo (used when not running as root)
#
# ENV VARIABLES:
#   SDK_ROOT (path): Voyager SDK checkout holding venv/ and VERSION.TXT.
#     Required: Yes.
#
# EXIT CODES:
#   0: Success.
#   1: SDK version could not be resolved, unsupported Ubuntu version, or a
#      command failed (set -e).
#   2: SDK_ROOT is not set.
#
# EXAMPLE:
#   SDK_ROOT=/opt/voyager-sdk bash deployment/monitor/setup.sh
set -euo pipefail

# Print a message prefixed with the script name.
#
# Arguments:
#   $@ (string): Message words.
#
# Outputs:
#   stdout: The prefixed message.
log() { echo "[monitor/setup.sh] $*"; }

if [[ -z "${SDK_ROOT:-}" ]]; then
  echo "ERROR: SDK_ROOT must be set in the environment" >&2
  exit 2
fi

SUDO_CMD=()
[[ "$EUID" != "0" ]] && SUDO_CMD=(sudo)

AXVERSION_BIN="$SDK_ROOT/venv/bin/axversion"
if [[ -x "$AXVERSION_BIN" ]]; then
  SDK_VERSION="$("$AXVERSION_BIN" 2>/dev/null || true)"
fi
if [[ -z "${SDK_VERSION:-}" && -f "$SDK_ROOT/VERSION.TXT" ]]; then
  SDK_VERSION="$(cat "$SDK_ROOT/VERSION.TXT")"
fi
if [[ -z "${SDK_VERSION:-}" ]]; then
  echo "ERROR: could not resolve the installed SDK version from $SDK_ROOT (tried axversion and VERSION.TXT)" >&2
  exit 1
fi
log "PHASE: resolve_version PASS (SDK_VERSION=$SDK_VERSION)"

MONITOR_PACKAGE="axelera-voyager-sdk-base-$SDK_VERSION"

AXELERA_APT_LIST="/etc/apt/sources.list.d/axelera.list"
AXELERA_APT_KEYRING="/etc/apt/keyrings/axelera.gpg"
if [[ -f "$AXELERA_APT_LIST" ]]; then
  log "PHASE: apt_repo SKIP (already present: $AXELERA_APT_LIST)"
else
  log "PHASE: apt_repo (adding Axelera apt source)"
  UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_ID%%.*}")"
  case "$UBUNTU_CODENAME" in
    22) APT_CODENAME="ubuntu22" ;;
    24) APT_CODENAME="ubuntu24" ;;
    *)
      echo "ERROR: unsupported Ubuntu major version '$UBUNTU_CODENAME' for the Axelera apt repo (expected 22 or 24)" >&2
      exit 1
      ;;
  esac
  "${SUDO_CMD[@]}" mkdir -p "$(dirname "$AXELERA_APT_KEYRING")"
  "${SUDO_CMD[@]}" sh -c "curl -fsSL https://software.axelera.ai/artifactory/api/security/keypair/axelera/public | gpg --dearmor -o '$AXELERA_APT_KEYRING'"
  "${SUDO_CMD[@]}" sh -c "echo 'deb [signed-by=$AXELERA_APT_KEYRING] https://software.axelera.ai/artifactory/axelera-apt-source $APT_CODENAME main' > '$AXELERA_APT_LIST'"
  log "PHASE: apt_repo PASS ($APT_CODENAME)"
fi

# Skip the install only when both packages are already present.
if dpkg -s "$MONITOR_PACKAGE" >/dev/null 2>&1 && dpkg -s libqt6svg6 >/dev/null 2>&1; then
  log "PHASE: install_package SKIP ($MONITOR_PACKAGE + libqt6svg6 already installed)"
else
  log "PHASE: install_package ($MONITOR_PACKAGE, libqt6svg6)"
  "${SUDO_CMD[@]}" apt-get update -qq
  "${SUDO_CMD[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$MONITOR_PACKAGE" libqt6svg6
  log "PHASE: install_package PASS"
fi

if "${SUDO_CMD[@]}" service axsystemserver status >/dev/null 2>&1; then
  log "PHASE: start_daemon SKIP (axsystemserver already running)"
else
  log "PHASE: start_daemon (service axsystemserver start)"
  "${SUDO_CMD[@]}" service axsystemserver start
  log "PHASE: start_daemon PASS"
fi

AXELERA_ACTIVATE_SCRIPT="/opt/axelera/sdk/$SDK_VERSION/axelera_activate.sh"
if [[ -f "$AXELERA_ACTIVATE_SCRIPT" ]]; then
  set +u
  source "$AXELERA_ACTIVATE_SCRIPT"
  set -u
  log "PHASE: activate_runtime PASS (PATH/LD_LIBRARY_PATH now include $AXELERA_RUNTIME_DIR)"
else
  log "WARNING: PHASE: activate_runtime SKIP ($AXELERA_ACTIVATE_SCRIPT not found -- axmonitor likely won't be on PATH)"
fi

log "PHASE: smoke_test (axmonitor --server-address 127.0.0.1:5555 --ui console -c print)"
if SMOKE_OUTPUT="$(axmonitor --server-address 127.0.0.1:5555 --ui console -c print 2>&1)"; then
  log "PHASE: smoke_test PASS, output:"
  echo "$SMOKE_OUTPUT"
else
  log "WARNING: PHASE: smoke_test did not exit cleanly -- axsystemserver may still be starting up. Output:"
  echo "$SMOKE_OUTPUT"
fi
