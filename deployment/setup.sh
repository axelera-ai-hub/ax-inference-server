#!/bin/bash
#
# Set up an Axelera Voyager SDK host, optionally inside a Docker container,
# and build and serve the inference server on it.
#
# With --target docker the script creates (or reuses) a container and re-runs
# itself inside it with --target host. With --target host it runs the setup
# phases directly. Phases that are already satisfied are skipped, so re-runs
# are safe. Run with --help for the full flag reference.
#
# USAGE:
#   ./setup.sh --target {host|docker} --sdk-repo-url <git-url> \
#              --sdk-dest-dir <path> --sdk-ref <branch|tag|sha> [options]
#   ./setup.sh --target host --place-yaml SRC DEST_DIR
#
# PHASES (in order):
#   install_driver         --driver, bare host only: install or upgrade metis-dkms
#                          from the Axelera apt repo, load the module, check binding.
#   ensure_container       docker target: create, restart or recreate the container
#                          and check its device-cgroup rules.
#   dispatch_to_container  docker target: exec this script in the container.
#   place_yaml             Copy a YAML file into a directory; exits afterwards
#                          unless an SDK repo URL was also given.
#   clone_checkout         Clone or fetch the SDK and check out --sdk-ref.
#   sudo_preflight         Prime sudo from SETUP_SUDO_PASSWORD when installs need it.
#   internal_sdk_ca        --internal-sdk: fetch and trust the internal CA cert.
#   install_deps           Run the SDK installer (skipped if the marker file exists).
#   server_build           cmake and ninja build of server/ against the SDK venv.
#   host_server_setup      Docker dispatch only: venv, .env and launch of host_server.py.
#   monitor_setup          --monitor, docker dispatch only: deployment/monitor/setup.sh.
#   vllm_axplugin_setup    --vllm-axplugin, docker dispatch only: .venv-vllm and axplugin.
#   compile_models         Run the SDK deploy.py on --model-config.
#   smoke_test             Always skipped; endpoint smoke tests are not done here.
#
# DEPENDENCIES:
#   - git, curl, python3 (SDK checkout, downloads, venvs)
#   - docker (target docker only)
#   - apt-get, dpkg, sudo (system packages)
#   - cmake, ninja, protobuf and gRPC dev packages (installed by the script)
#   - aws CLI (--internal-sdk only; installed if missing)
#
# ARGUMENTS:
#   --target (host|docker): Where to run setup. Required.
#   --sdk-repo-url, --sdk-dest-dir, --sdk-ref (string): SDK source, destination
#     and ref. Required for host setup.
#   --container-name (string): Container name. Defaults to inference-server-sdk190.
#   --project-dir (path): Repo path mounted into the container. Defaults to the
#     repository root.
#   --restart, --force-recreate-container (flags): Docker container handling.
#   --force-reinstall-sdk, --force-rebuild-server (flags): Redo SDK install or
#     the server build from scratch.
#   --model-config (path), --deploy-args (string), --skip-compile (flag):
#     Model compile step.
#   --place-yaml SRC DEST_DIR (paths): Copy SRC into DEST_DIR.
#   --internal-sdk, --driver, --monitor, --vllm-axplugin (flags): Optional phases.
#   --skip-smoketest, --smoke-endpoints, --smoke-image, --smoke-batch-size:
#     Accepted and ignored.
#
# ENV VARIABLES:
#   SETUP_SUDO_PASSWORD (string): sudo password used to prime sudo when there is
#     no TTY. Required: No.
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN (string): Needed
#     with --internal-sdk to fetch the CA cert (token only for temporary
#     credentials). Required: Only with --internal-sdk.
#   SETUP_INSIDE_DOCKER_DISPATCH (0|1): Set by this script when it re-runs
#     itself in the container; not meant to be set by hand.
#   SETUP_HOST_OPENCL_AVAILABLE (0|1): Set by this script for the in-container
#     run; not meant to be set by hand.
#
# EXIT CODES:
#   0: Success (also --help, and --place-yaml without an SDK URL).
#   1: A phase failed.
#   2: Invalid arguments.
#
# EXAMPLE:
#   SETUP_SUDO_PASSWORD=... ./setup.sh --target docker \
#     --sdk-repo-url https://github.com/axelera-ai-hub/voyager-sdk.git \
#     --sdk-dest-dir /opt/sdk --sdk-ref v1.5.0
set -euo pipefail

ORIGINAL_ARGS=("$@")

# Print the usage text.
#
# Outputs:
#   stdout: The usage text (the caller redirects to stderr on errors).
#
# Returns:
#   0: Success.
usage() {
  cat <<'EOF'
Usage: setup.sh --target {host|docker} --sdk-repo-url <git-url> \
                 --sdk-dest-dir <path> --sdk-ref <branch|tag|sha> \
                 [--container-name NAME] [--project-dir PATH] \
                 [--restart] [--force-recreate-container] [--force-reinstall-sdk] \
                 [--force-rebuild-server] \
                 [--model-config PATH] [--deploy-args "..."] \
                 [--skip-compile] [--skip-smoketest] \
                 [--smoke-endpoints host:port[,host:port...]] \
                 [--smoke-image PATH] [--smoke-batch-size N] \
                 [--place-yaml SRC DEST_DIR] [--internal-sdk] [--driver] [--monitor] \
                 [--vllm-axplugin]

  --target host|docker   Where to run setup. "docker" reuses the named
                          container if it already exists, else creates it,
                          then re-execs this script inside it with
                          --target host. "docker" ALSO sets up and launches
                          host_server.py inside that same container, in its
                          own separate venv, bound to 0.0.0.0:8088 (API key
                          generated into deployment/.env on first run) --
                          host_server.py must share the SDK's namespace, so
                          this only happens for "docker"; a plain "host" run
                          (e.g. a bare-metal host) leaves host_server.py setup
                          to be done separately.
  --sdk-repo-url URL      git URL to clone the SDK from (HTTPS or SSH).
                          Examples:
                            https://github.com/axelera-ai-hub/voyager-sdk.git
                            git@github.com:axelera-ai/internal-voyager-sdk.git
  --sdk-dest-dir PATH     Destination directory for the clone. If an SDK is
                          already set up here (clone + install_deps marker
                          present), it is reused as-is -- see
                          --force-reinstall-sdk to override.
  --sdk-ref REF           Branch, tag, or commit SHA to check out.
  --container-name NAME   Docker container name (default: inference-server-sdk190).
  --project-dir PATH      Host path mounted into the container at the same
                          path (default: dirname of this script's grandparent,
                          i.e. the inference_server repo root).
  --restart               --target docker only: if the named container
                          already exists, `docker restart` it (not
                          recreate) before continuing. Clears any stuck
                          process or held device file descriptor inside the
                          container's namespace (e.g. a wedged axdevice/
                          axrunmodel handle left by a crashed or zombie
                          process) without losing the container's
                          filesystem/image layer or needing
                          --force-recreate-container. The container's own
                          PID 1 is `sleep infinity`, not host_server.py, so
                          a restart kills host_server.py too -- the
                          host_server_setup phase below already detects it's
                          down (its own health check fails) and relaunches
                          it automatically, no separate step needed. No-op
                          if the container doesn't exist yet (falls through
                          to the normal create path).
  --force-recreate-container
                          --target docker only: remove the existing
                          container (docker rm -f) and recreate it fresh,
                          instead of reusing it.
  --force-reinstall-sdk   Remove the existing --sdk-dest-dir (if any) and
                          redo clone + install_deps from scratch, instead of
                          reusing what's already there.
  --force-rebuild-server  server_build phase only: delete server/build and
                          do a full from-scratch cmake+ninja build, instead
                          of the default incremental behavior (see "Phase:
                          server build" below -- without this flag, setup.sh
                          still always re-invokes cmake/ninja so a source
                          change under server/ gets picked up, it just lets
                          Ninja decide what actually needs recompiling rather
                          than wiping the build dir first).
  --model-config PATH     Vendor network YAML forwarded to deploy.py as the
                          positional "network" argument.
  --deploy-args "..."     Extra args forwarded verbatim to deploy.py (e.g.
                          "--mode QUANTCOMPILE --metis --pipe torch-aipu").
  --skip-compile          Skip the deploy.py model-compile phase.
  --skip-smoketest        No-op (see "Phase: smoke test" below for why);
                          accepted only so callers don't need to change.
  --smoke-endpoints LIST  No-op (ditto). setup.sh no longer smoke-tests
                          endpoints -- that's not its job.
  --smoke-image PATH      No-op (ditto).
  --smoke-batch-size N    No-op (ditto). Still accepted with a default so
                          host_server.py's /api/v1/setup, which always
                          forwards this flag, doesn't start failing argument
                          parsing outright.
  --place-yaml SRC DEST_DIR
                          Copy SRC into DEST_DIR (created if missing). Used
                          by the FastAPI server after an upload; can also be
                          run standalone.
  --internal-sdk          This SDK ref is an internal/pre-release build whose
                          installer fetches its apt signing key over HTTPS
                          from an internal-only host (requires a CA cert this
                          image does not trust by default). Before
                          install_deps runs, fetch that CA cert from S3 and
                          trust it. Internal SDK releases need ONLY
                          SETUP_SUDO_PASSWORD plus AWS credentials (below) --
                          nothing else manual.
  --driver                Install the Metis kernel driver (metis-dkms) via
                          apt on the bare host before anything else, using
                          Axelera's own apt repo (see docs/user-guides/
                          sdk-install.md "Option b" in the SDK repo). Runs
                          exactly once on the genuine bare host regardless of
                          --target host|docker (never inside the container).
                          Needs sudo for apt -- see SETUP_SUDO_PASSWORD below.
                          Idempotent: reads the installed driver version
                          (modinfo metis, else dpkg) and the SDK's
                          RELEASE_COMPATIBILITY_MATRIX.md (from --sdk-ref) and
                          skips the apt install only when the installed version
                          satisfies the matrix's Linux driver column for this
                          SDK release; a missing or too-old driver is
                          (re)installed at the recommended version. It still
                          ensures the module is loaded (modprobe) and persists
                          across reboots (/etc/modules-load.d/metis.conf).
  --monitor               --target docker only: also install and start
                          AxMonitor (axmonitor CLI + axsystemserver daemon)
                          inside the container, via deployment/monitor/setup.sh.
                          This is a separate apt-package install
                          (axelera-voyager-sdk-base-<SDK version>), independent
                          of the pip-based SDK runtime install above -- see
                          deployment/monitor/setup.sh for details. No-op for a
                          plain --target host run.
  --vllm-axplugin         --target docker only: also set up vLLM/axplugin
                          HTTP-served LLM/VLM serving -- a second, isolated
                          venv (.venv-vllm) with a CPU-pinned torch/vllm
                          build (kept out of the SDK's own shared venv, whose
                          torch is a transformers dependency and a different
                          version), borrowing the SDK venv's
                          axelera.runtime/axelera.firmware via a .pth file,
                          then `pip install -e server/vllm/axelera` into it.
                          See server/quickstart.md for the manual equivalent
                          and how to then serve a model with it. No-op for a
                          plain --target host run.

Environment:
  SETUP_SUDO_PASSWORD     Optional. install_deps shells out to the SDK's own
                          installer, which calls sudo for apt packages; with
                          no TTY (non-interactive runs), an uncached sudo
                          credential fails outright. Set this to have
                          setup.sh prime sudo non-interactively instead of
                          failing with instructions. Never put it on the
                          command line, in a file, or in a commit.
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
                          Required when --internal-sdk is set (SESSION_TOKEN
                          only if your credentials are temporary/STS-issued).
                          Used solely to `aws s3 cp` the internal CA cert.
                          Never put these on the command line, in a file, or
                          in a commit.
EOF
}

TARGET=""
SDK_REPO_URL=""
SDK_DEST_DIR=""
SDK_REF=""
CONTAINER_NAME="inference-server-sdk190"
PROJECT_DIR=""
RESTART_CONTAINER=0
FORCE_RECREATE_CONTAINER=0
FORCE_REINSTALL_SDK=0
FORCE_REBUILD_SERVER=0
MODEL_CONFIG=""
DEPLOY_ARGS=""
SKIP_COMPILE=0
SKIP_SMOKETEST=0
SMOKE_ENDPOINTS=""
SMOKE_IMAGE=""
SMOKE_BATCH_SIZE=1
PLACE_YAML_SRC=""
PLACE_YAML_DEST=""
INTERNAL_SDK=0
INSTALL_DRIVER=0
MONITOR=0
VLLM_AXPLUGIN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --sdk-repo-url) SDK_REPO_URL="$2"; shift 2 ;;
    --sdk-dest-dir) SDK_DEST_DIR="$2"; shift 2 ;;
    --sdk-ref) SDK_REF="$2"; shift 2 ;;
    --container-name) CONTAINER_NAME="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --restart) RESTART_CONTAINER=1; shift ;;
    --force-recreate-container) FORCE_RECREATE_CONTAINER=1; shift ;;
    --force-reinstall-sdk) FORCE_REINSTALL_SDK=1; shift ;;
    --force-rebuild-server) FORCE_REBUILD_SERVER=1; shift ;;
    --model-config) MODEL_CONFIG="$2"; shift 2 ;;
    --deploy-args) DEPLOY_ARGS="$2"; shift 2 ;;
    --skip-compile) SKIP_COMPILE=1; shift ;;
    --skip-smoketest) SKIP_SMOKETEST=1; shift ;;
    --smoke-endpoints) SMOKE_ENDPOINTS="$2"; shift 2 ;;
    --smoke-image) SMOKE_IMAGE="$2"; shift 2 ;;
    --smoke-batch-size) SMOKE_BATCH_SIZE="$2"; shift 2 ;;
    --place-yaml) PLACE_YAML_SRC="$2"; PLACE_YAML_DEST="$3"; shift 3 ;;
    --internal-sdk) INTERNAL_SDK=1; shift ;;
    --driver) INSTALL_DRIVER=1; shift ;;
    --monitor) MONITOR=1; shift ;;
    --vllm-axplugin) VLLM_AXPLUGIN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: --target is required" >&2
  exit 2
fi

if [[ "$RESTART_CONTAINER" == "1" && "$TARGET" != "docker" ]]; then
  echo "ERROR: --restart is only valid with --target docker" >&2
  exit 2
fi

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$REPO_ROOT}"

# Print a message prefixed with the script name.
#
# Arguments:
#   $@ (string): Message words.
#
# Outputs:
#   stdout: The prefixed message.
log() { echo "[setup.sh] $*"; }

# Preseed tzdata as Etc/UTC and install it so later apt installs do not prompt.
#
# Uses sudo unless running as root. Failures of the final apt-get are ignored.
#
# Returns:
#   0: Success.
_preseed_tzdata_noninteractive() {
  local sudo_cmd=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  "${sudo_cmd[@]}" bash -c '
    echo "tzdata tzdata/Areas select Etc" | debconf-set-selections
    echo "tzdata tzdata/Zones/Etc select UTC" | debconf-set-selections
    ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tzdata >/dev/null 2>&1 || true
  '
}

# Install pciutils (lspci) and kmod (lsmod) when those commands are missing.
#
# Install failures are ignored.
#
# Returns:
#   0: Always.
_ensure_pciutils() {
  local sudo_cmd=() pkgs=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  command -v lspci >/dev/null 2>&1 || pkgs+=(pciutils)
  command -v lsmod >/dev/null 2>&1 || pkgs+=(kmod)
  [[ ${#pkgs[@]} -eq 0 ]] && return 0
  DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq "${pkgs[@]}" >/dev/null 2>&1 || true
}

# Install numactl when it is missing.
#
# Install failures are ignored.
#
# Returns:
#   0: Always.
_ensure_numactl() {
  local sudo_cmd=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  command -v numactl >/dev/null 2>&1 && return 0
  DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq numactl >/dev/null 2>&1 || true
}

# Install the packages needed to build server/: cmake, ninja, pkg-config, ffmpeg,
# gRPC, protobuf, gperftools, libjpeg, libturbojpeg and liburing development files.
#
# Only missing packages are installed; install failures are ignored.
#
# Returns:
#   0: Always.
_ensure_server_build_tools() {
  local sudo_cmd=() pkgs=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  command -v cmake >/dev/null 2>&1 || pkgs+=(cmake)
  command -v ninja >/dev/null 2>&1 || pkgs+=(ninja-build)
  command -v pkg-config >/dev/null 2>&1 || pkgs+=(pkg-config)
  command -v ffmpeg >/dev/null 2>&1 || pkgs+=(ffmpeg)
  dpkg -s libgrpc++-dev >/dev/null 2>&1 || pkgs+=(libgrpc++-dev)
  command -v protoc >/dev/null 2>&1 || pkgs+=(protobuf-compiler)
  dpkg -s protobuf-compiler-grpc >/dev/null 2>&1 || pkgs+=(protobuf-compiler-grpc)
  dpkg -s libprotobuf-dev >/dev/null 2>&1 || pkgs+=(libprotobuf-dev)
  dpkg -s libgoogle-perftools-dev >/dev/null 2>&1 || pkgs+=(libgoogle-perftools-dev)
  dpkg -s libjpeg-dev >/dev/null 2>&1 || pkgs+=(libjpeg-dev)
  dpkg -s libturbojpeg0-dev >/dev/null 2>&1 || pkgs+=(libturbojpeg0-dev)
  dpkg -s liburing-dev >/dev/null 2>&1 || pkgs+=(liburing-dev)
  [[ ${#pkgs[@]} -eq 0 ]] && return 0
  DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq "${pkgs[@]}" >/dev/null 2>&1 || true
}

# Install gir1.2-glib-2.0 and gobject-introspection when libgirepository-1.0.so.1
# is not in the linker cache.
#
# Install failures are ignored.
#
# Returns:
#   0: Always.
_ensure_gobject_introspection() {
  local sudo_cmd=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  ldconfig -p 2>/dev/null | grep -q 'libgirepository-1\.0\.so\.1' && return 0
  DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq gir1.2-glib-2.0 gobject-introspection >/dev/null 2>&1 || true
}

# Check whether the host has an OpenCL-capable GPU setup.
#
# True when a /dev/dri/render* node and an OpenCL ICD file in
# /etc/OpenCL/vendors exist.
#
# Returns:
#   0: OpenCL appears available.
#   1: Otherwise.
_host_opencl_available() {
  ls /dev/dri/render* >/dev/null 2>&1 || return 1
  ls /etc/OpenCL/vendors/*.icd >/dev/null 2>&1 || return 1
  return 0
}

# Install the mesa and Intel OpenCL ICD packages when missing.
#
# Install failures are ignored.
#
# Returns:
#   0: Always.
_ensure_opencl_runtime() {
  local sudo_cmd=() pkgs=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  dpkg -s mesa-opencl-icd >/dev/null 2>&1 || pkgs+=(mesa-opencl-icd)
  dpkg -s intel-opencl-icd >/dev/null 2>&1 || pkgs+=(intel-opencl-icd)
  [[ ${#pkgs[@]} -eq 0 ]] && return 0
  DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq "${pkgs[@]}" >/dev/null 2>&1 || true
}

# Compare two versions with sort -V.
#
# Arguments:
#   $1 (string): Version to test.
#   $2 (string): Minimum version.
#
# Returns:
#   0: $1 is greater than or equal to $2.
#   1: $1 is lower than $2.
version_ge() { [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" == "$2" ]]; }

# Print a file from the SDK repository.
#
# Uses the copy in the SDK destination directory when present; otherwise does a
# shallow, blob-less fetch of the SDK ref into a temporary repository and reads
# the file from it.
#
# Arguments:
#   $1 (string): File path relative to the SDK repository root.
#
# Globals:
#   SDK_DEST_DIR, SDK_REPO_URL, SDK_REF (string): read.
#
# Outputs:
#   stdout: The file contents.
#
# Returns:
#   0: File printed.
#   1: File unavailable.
sdk_file() {
  local file="$1" tmp out=""
  if [[ -f "${SDK_DEST_DIR:-/nonexistent}/$file" ]]; then
    cat "$SDK_DEST_DIR/$file"; return 0
  fi
  [[ -n "${SDK_REPO_URL:-}" && -n "${SDK_REF:-}" ]] || return 1
  tmp="$(mktemp -d)"
  if git -C "$tmp" init -q 2>/dev/null \
     && git -C "$tmp" fetch -q --depth 1 --filter=blob:none "$SDK_REPO_URL" "$SDK_REF" 2>/dev/null \
     && out="$(git -C "$tmp" show "FETCH_HEAD:$file" 2>/dev/null)"; then
    rm -rf "$tmp"; printf '%s\n' "$out"; return 0
  fi
  rm -rf "$tmp"; return 1
}

# Work out the Metis driver version this SDK release needs.
#
# Reads VERSION.TXT and RELEASE_COMPATIBILITY_MATRIX.md through sdk_file, finds
# the matrix row for the SDK version and takes the recommended driver (column 7)
# and the list of supported drivers (column 8). The minimum is the lowest of them
# by sort -V.
#
# Globals:
#   SDK_REF (string): read, for messages.
#   DRIVER_REQ_RECOMMENDED (string): set.
#   DRIVER_REQ_MIN (string): set.
#
# Outputs:
#   stdout: Log lines describing the requirement.
#
# Returns:
#   0: Requirement found.
#   1: Files unavailable or no row for this SDK release.
load_driver_requirement() {
  local ver matrix row supported
  ver="$(sdk_file VERSION.TXT | head -1 | tr -d '[:space:]' | sed 's/^v//; s/[-+].*//')" || true
  matrix="$(sdk_file RELEASE_COMPATIBILITY_MATRIX.md)" || true
  if [[ -z "$ver" || -z "$matrix" ]]; then
    log "driver check: no VERSION.TXT / RELEASE_COMPATIBILITY_MATRIX.md available at ${SDK_REF:-<no --sdk-ref>}"
    return 1
  fi
  row="$(awk -F'|' -v want="v$ver" '{ for (i=1;i<=NF;i++) gsub(/^[ \t]+|[ \t]+$/, "", $i) } $2 == want { print $7 "|" $8; exit }' <<< "$matrix")"
  DRIVER_REQ_RECOMMENDED="${row%%|*}"
  supported="${row#*|}"
  if [[ -z "$DRIVER_REQ_RECOMMENDED" ]]; then
    log "driver check: SDK release v$ver has no row in RELEASE_COMPATIBILITY_MATRIX.md"
    return 1
  fi
  DRIVER_REQ_MIN="$(printf '%s\n' "$DRIVER_REQ_RECOMMENDED" $(tr ',' ' ' <<< "$supported") | sort -V | head -1)"
  log "driver check: SDK v$ver needs metis-dkms >= $DRIVER_REQ_MIN (recommended $DRIVER_REQ_RECOMMENDED)"
}

if [[ "$INSTALL_DRIVER" == "1" && -z "${SETUP_INSIDE_DOCKER_DISPATCH:-}" ]]; then
  sudo_cmd=()
  [[ "$EUID" != "0" ]] && sudo_cmd=(sudo)
  if [[ "$EUID" != "0" ]] && ! sudo -n true 2>/dev/null; then
    if [[ -n "${SETUP_SUDO_PASSWORD:-}" ]]; then
      log "PHASE: install_driver (priming sudo credential from SETUP_SUDO_PASSWORD)"
      if ! printf '%s\n' "$SETUP_SUDO_PASSWORD" | sudo -S -p '' true; then
        echo "ERROR: sudo authentication failed with the supplied SETUP_SUDO_PASSWORD" >&2
        exit 1
      fi
      unset SETUP_SUDO_PASSWORD
    else
      {
        echo "ERROR: --driver needs sudo (for apt packages) but this session has no"
        echo "cached sudo credential and no password was supplied. Do ONE of:"
        echo ""
        echo "  1) Run this exact command yourself, interactively (you'll be prompted):"
        echo "       sudo bash \"$SCRIPT_PATH\" ${ORIGINAL_ARGS[*]}"
        echo ""
        echo "  2) Re-run with your sudo password available non-interactively (never put"
        echo "     the password on the command line, in a file, or in a commit):"
        echo "       SETUP_SUDO_PASSWORD='<your password>' bash \"$SCRIPT_PATH\" ${ORIGINAL_ARGS[*]}"
        echo ""
        echo "  3) Configure passwordless sudo for apt-get on this host once, then re-run"
        echo "     with no password needed at all."
      } >&2
      exit 1
    fi
  fi

  DPKG_STATE="$(dpkg -l metis-dkms 2>/dev/null || true)"
  PKG_VER=""
  grep -q '^ii' <<< "$DPKG_STATE" && PKG_VER="$(dpkg-query -W -f='${Version}' metis-dkms 2>/dev/null || true)"
  MOD_VER="$(modinfo -F version metis 2>/dev/null || true)"
  INSTALLED_VER="${MOD_VER:-$PKG_VER}"
  INSTALLED_VER="${INSTALLED_VER%%[-+~]*}"

  NEED_INSTALL=1
  if [[ -z "$INSTALLED_VER" ]]; then
    log "driver check: no Metis driver installed"
  elif load_driver_requirement; then
    if version_ge "$INSTALLED_VER" "$DRIVER_REQ_MIN"; then
      log "PHASE: install_driver SKIP (installed metis driver $INSTALLED_VER satisfies the compatibility matrix: >= $DRIVER_REQ_MIN)"
      NEED_INSTALL=0
    else
      log "driver check: installed metis driver $INSTALLED_VER is older than the required $DRIVER_REQ_MIN -- upgrading"
    fi
  else
    log "PHASE: install_driver SKIP (metis driver $INSTALLED_VER is installed but the compatibility matrix is unavailable, so its version cannot be checked)"
    NEED_INSTALL=0
  fi

  if [[ "$NEED_INSTALL" == "1" ]]; then
    log "PHASE: install_driver (adding Axelera apt repo + installing metis-dkms)"
    "${sudo_cmd[@]}" mkdir -p /etc/apt/keyrings
    "${sudo_cmd[@]}" sh -c "curl -fsSL https://software.axelera.ai/artifactory/api/security/keypair/axelera/public | gpg --dearmor -o /etc/apt/keyrings/axelera.gpg"
    UBUNTU_CODENAME_SUFFIX=$(. /etc/os-release && { [[ "$VERSION_ID" == "22.04" ]] && echo ubuntu22 || echo ubuntu24; })
    "${sudo_cmd[@]}" sh -c "echo 'deb [signed-by=/etc/apt/keyrings/axelera.gpg] https://software.axelera.ai/artifactory/axelera-apt-source $UBUNTU_CODENAME_SUFFIX main' > /etc/apt/sources.list.d/axelera.list"
    "${sudo_cmd[@]}" apt-get update -qq
    DRIVER_PKG=metis-dkms
    if [[ -n "${DRIVER_REQ_RECOMMENDED:-}" ]]; then
      PINNED_VER="$(apt-cache madison metis-dkms 2>/dev/null | awk -v v="$DRIVER_REQ_RECOMMENDED" '{ split($3, a, /[-+~]/); if (a[1] == v) { print $3; exit } }')"
      [[ -n "$PINNED_VER" ]] && DRIVER_PKG="metis-dkms=$PINNED_VER"
    fi
    DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y -qq "$DRIVER_PKG"
    NEW_PKG_VER="$(dpkg-query -W -f='${Version}' metis-dkms 2>/dev/null || true)"
    LOADED_VER="$(modinfo -F version metis 2>/dev/null || true)"
    if [[ -n "$INSTALLED_VER" && -n "$(lsmod | grep '^metis' || true)" && "${NEW_PKG_VER%%[-+~]*}" != "${INSTALLED_VER}" ]]; then
      log "WARNING: metis-dkms is now $NEW_PKG_VER, but the previously loaded module ($INSTALLED_VER) stays loaded until it is reloaded -- reboot, or stop every Metis user and run: sudo rmmod metis && sudo modprobe metis"
    fi
  fi

  LSMOD_OUT="$(lsmod)"
  if ! grep -q '^metis' <<< "$LSMOD_OUT"; then
    "${sudo_cmd[@]}" modprobe metis
  fi
  [[ -f /etc/modules-load.d/metis.conf ]] || echo metis | "${sudo_cmd[@]}" tee /etc/modules-load.d/metis.conf >/dev/null
  LSMOD_OUT="$(lsmod)"
  grep -q '^metis' <<< "$LSMOD_OUT" || { echo "ERROR: metis module still not loaded after modprobe" >&2; exit 1; }

  METIS_PCI="$(lspci -nn -d 1f9d:1100 2>/dev/null || true)"
  if [[ -z "$METIS_PCI" ]]; then
    log "WARNING: install_driver PASS, but no 1f9d:1100 PCI device found on this host to bind it to"
  else
    LSPCI_OUT="$(lspci -nnk -d 1f9d:1100)"
    grep -q 'Kernel driver in use: axl' <<< "$LSPCI_OUT" \
      || { echo "ERROR: no 1f9d:1100 device bound to the axl/metis driver" >&2; echo "$LSPCI_OUT" >&2; exit 1; }
    log "PHASE: install_driver PASS (metis-dkms installed, module loaded, device(s) bound to axl)"
  fi
fi

# Print the host's upstream IPv4 DNS servers, one per line.
#
# Takes them from resolvectl for the default-route interface, else from
# /run/systemd/resolve/resolv.conf, else /etc/resolv.conf. Loopback addresses
# are dropped and duplicates removed.
#
# Outputs:
#   stdout: Nameserver addresses.
_container_dns_candidates() {
  local dev out
  dev="$(ip -4 route show default 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1); exit}}')"
  if [[ -n "$dev" ]] && command -v resolvectl >/dev/null 2>&1; then
    out="$(resolvectl dns "$dev" 2>/dev/null | sed 's/^[^:]*://' | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')"
  fi
  if [[ -z "${out:-}" && -r /run/systemd/resolve/resolv.conf ]]; then
    out="$(awk '$1=="nameserver"{print $2}' /run/systemd/resolve/resolv.conf | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')"
  fi
  if [[ -z "${out:-}" ]]; then
    out="$(awk '$1=="nameserver"{print $2}' /etc/resolv.conf | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')"
  fi
  printf '%s\n' "$out" | grep -v -E '^127\.' | awk '!seen[$0]++'
}

# Query a DNS server directly for an A record, using a small python3 script.
#
# Arguments:
#   $1 (string): Nameserver IPv4 address (port 53, 2 s timeout).
#   $2 (string): Hostname to resolve.
#
# Outputs:
#   stdout: A if the answer has an A record, CNAME if it has a CNAME but no A
#     record, otherwise NONE (also on timeouts and error replies).
#
# Returns:
#   0: Always.
_dns_probe() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null || echo NONE
import socket, struct, sys, random
ns, name = sys.argv[1:3]
tid = random.randrange(65536)
q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0" + struct.pack(">HH", 1, 1)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
try:
    s.sendto(q, (ns, 53)); d = s.recv(4096)
except Exception:
    print("NONE"); sys.exit()
if d[3] & 15 != 0:
    print("NONE"); sys.exit()
an = struct.unpack(">H", d[6:8])[0]
def skip(o):
    while True:
        l = d[o]
        if l == 0: return o + 1
        if l & 0xC0 == 0xC0: return o + 2
        o += l + 1
o = skip(12) + 4
types = set()
for _ in range(an):
    o = skip(o); t, _c, _ttl, rl = struct.unpack(">HHIH", d[o:o+10]); types.add(t); o += 10 + rl
print("A" if 1 in types else ("CNAME" if 5 in types else "NONE"))
PY
}

# Choose up to three DNS servers for the container.
#
# Each candidate is probed for download.pytorch.org. Servers returning an A record
# rank first; servers returning only a CNAME, or none but still resolving
# pypi.org, rank second.
#
# Globals:
#   CONTAINER_DNS_SERVERS (array): set.
_pick_container_dns() {
  local ns r complete=() partial=()
  CONTAINER_DNS_SERVERS=()
  while read -r ns; do
    [[ -z "$ns" ]] && continue
    r="$(_dns_probe "$ns" download.pytorch.org)"
    if [[ "$r" == "A" ]]; then complete+=("$ns")
    elif [[ "$r" == "CNAME" ]]; then partial+=("$ns")
    else
      [[ "$(_dns_probe "$ns" pypi.org)" != "NONE" ]] && partial+=("$ns")
    fi
  done < <(_container_dns_candidates)
  CONTAINER_DNS_SERVERS=("${complete[@]}" "${partial[@]}")
  CONTAINER_DNS_SERVERS=("${CONTAINER_DNS_SERVERS[@]:0:3}")
}

# Check whether any chosen DNS server resolves a host to an IPv4 address.
#
# Arguments:
#   $1 (string): Hostname.
#
# Globals:
#   CONTAINER_DNS_SERVERS (array): read.
#
# Returns:
#   0: At least one server returns an A record.
#   1: None does.
_container_resolves_v4() {
  local ns
  for ns in "${CONTAINER_DNS_SERVERS[@]}"; do
    [[ "$(_dns_probe "$ns" "$1")" == "A" ]] && return 0
  done
  return 1
}

if [[ "$TARGET" == "docker" ]]; then
  HOST_OPENCL_AVAILABLE=0
  if _host_opencl_available; then
    HOST_OPENCL_AVAILABLE=1
    log "PHASE: ensure_container (host OpenCL detected -- will wire OpenCL into the container)"
  fi
  if [[ "$FORCE_RECREATE_CONTAINER" == "1" ]] && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    log "PHASE: ensure_container (--force-recreate-container: removing existing $CONTAINER_NAME)"
    docker rm -f "$CONTAINER_NAME" >/dev/null
  elif [[ "$RESTART_CONTAINER" == "1" ]] && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    log "PHASE: ensure_container (--restart: restarting $CONTAINER_NAME)"
    docker restart "$CONTAINER_NAME" >/dev/null
    RESTARTED_UP=0
    for i in $(seq 1 30); do
      docker exec "$CONTAINER_NAME" true >/dev/null 2>&1 && { RESTARTED_UP=1; break; }
      sleep 1
    done
    if [[ "$RESTARTED_UP" != "1" ]]; then
      echo "ERROR: $CONTAINER_NAME did not come back up after docker restart" >&2
      exit 1
    fi
    log "PHASE: ensure_container (--restart: $CONTAINER_NAME back up)"
  fi
  if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    log "PHASE: ensure_container (creating $CONTAINER_NAME)"
    DEVICE_CGROUP_ARGS=()
    SAMPLE_METIS_DEV="$(ls /dev/metis-*-*-0 2>/dev/null | head -1 || true)"
    if [[ -n "$SAMPLE_METIS_DEV" ]]; then
      METIS_MAJOR=$((16#$(stat -c '%t' "$SAMPLE_METIS_DEV")))
      DEVICE_CGROUP_ARGS+=(--device-cgroup-rule="c $METIS_MAJOR:* rmw")
    else
      log "WARNING: no /dev/metis-* device nodes found on this host -- creating container without a metis device-cgroup-rule"
    fi
    if [[ -e /dev/dma_heap/system ]]; then
      DMAHEAP_MAJOR=$((16#$(stat -c '%t' /dev/dma_heap/system)))
      DEVICE_CGROUP_ARGS+=(--device-cgroup-rule="c $DMAHEAP_MAJOR:* rmw")
    fi
    if [[ "$HOST_OPENCL_AVAILABLE" == "1" ]]; then
      SAMPLE_DRI_DEV="$(ls /dev/dri/render* 2>/dev/null | head -1 || true)"
      if [[ -n "$SAMPLE_DRI_DEV" ]]; then
        DRI_MAJOR=$((16#$(stat -c '%t' "$SAMPLE_DRI_DEV")))
        DEVICE_CGROUP_ARGS+=(--device-cgroup-rule="c $DRI_MAJOR:* rmw")
      fi
    fi
    DNS_ARGS=()
    _pick_container_dns
    if (( ${#CONTAINER_DNS_SERVERS[@]} )); then
      for _ns in "${CONTAINER_DNS_SERVERS[@]}"; do DNS_ARGS+=(--dns "$_ns"); done
      log "container DNS: ${CONTAINER_DNS_SERVERS[*]}"
    else
      log "WARNING: found no working IPv4 upstream resolver on the host -- container inherits Docker's default resolver config"
    fi
    ADD_HOST_ARGS=()
    PYPI_IP="$(getent ahostsv4 pypi.org 2>/dev/null | awk '{print $1}' | sort -u | head -1)"
    if [[ -n "$PYPI_IP" ]]; then
      ADD_HOST_ARGS+=(--add-host "pypi.org:$PYPI_IP")
    else
      log "WARNING: host cannot resolve an IPv4 address for pypi.org -- container will inherit whatever pypi.org resolution the container's own resolver produces"
    fi
    for PYTORCH_DL_HOST in download.pytorch.org download-r2.pytorch.org; do
      if (( ${#CONTAINER_DNS_SERVERS[@]} )) && _container_resolves_v4 "$PYTORCH_DL_HOST"; then
        continue
      fi
      PYTORCH_DL_IP="$(getent ahostsv4 "$PYTORCH_DL_HOST" 2>/dev/null | awk '{print $1}' | sort -u | head -1)"
      if [[ -n "$PYTORCH_DL_IP" ]]; then
        ADD_HOST_ARGS+=(--add-host "$PYTORCH_DL_HOST:$PYTORCH_DL_IP")
      else
        log "WARNING: host cannot resolve an IPv4 address for $PYTORCH_DL_HOST -- container will inherit whatever resolution the container's own resolver produces"
      fi
    done
    if [[ "$INTERNAL_SDK" == "1" ]]; then
      ARTIFACTORY_HOST="artifactory.production.aws.axelera.ai"
      ARTIFACTORY_IP="$(getent hosts "$ARTIFACTORY_HOST" 2>/dev/null | awk '{print $1}' | head -1)"
      if (( ${#CONTAINER_DNS_SERVERS[@]} )) && _container_resolves_v4 "$ARTIFACTORY_HOST"; then
        :
      elif [[ -n "$ARTIFACTORY_IP" ]]; then
        ADD_HOST_ARGS+=(--add-host "$ARTIFACTORY_HOST:$ARTIFACTORY_IP")
      else
        log "WARNING: host cannot resolve $ARTIFACTORY_HOST -- container will inherit the same failure"
      fi
    fi
    docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
      -v "$PROJECT_DIR:$PROJECT_DIR" -v /dev:/dev -v /sys:/sys \
      "${DEVICE_CGROUP_ARGS[@]}" --cap-add SYS_NICE --cap-add SYS_PTRACE --cap-add SYS_ADMIN --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
      --ulimit nofile=65536:1048576 \
      --sysctl net.ipv6.conf.all.disable_ipv6=1 \
      "${DNS_ARGS[@]}" "${ADD_HOST_ARGS[@]}" \
      -v ~/.ssh:/root/.ssh:ro \
      ubuntu:22.04 sleep infinity
    for _h in archive.ubuntu.com pypi.org github.com; do
      if ! timeout 20 docker exec "$CONTAINER_NAME" getent ahostsv4 "$_h" >/dev/null 2>&1; then
        log "ERROR: container cannot resolve $_h (resolver: $(docker exec "$CONTAINER_NAME" sed -n 's/^nameserver //p' /etc/resolv.conf | tr '\n' ' '))"
        exit 1
      fi
    done
    log "PHASE: ensure_container (bootstrapping baseline packages: git, python3, curl)"
    timeout 900 docker exec "$CONTAINER_NAME" bash -c \
      'apt-get -o Acquire::http::Timeout=30 -o Acquire::Retries=2 update -qq && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::http::Timeout=30 install -qq -y git ca-certificates python3 python3-venv python3-pip curl sudo >/dev/null'
    log "PHASE: ensure_container PASS (created)"
  else
    EXISTING_CGROUP_RULES="$(docker inspect "$CONTAINER_NAME" --format '{{.HostConfig.DeviceCgroupRules}}' 2>/dev/null || true)"
    STALE_DEVICES=()
    SAMPLE_METIS_DEV="$(ls /dev/metis-*-*-0 2>/dev/null | head -1 || true)"
    if [[ -n "$SAMPLE_METIS_DEV" ]]; then
      LIVE_METIS_MAJOR=$((16#$(stat -c '%t' "$SAMPLE_METIS_DEV")))
      [[ "$EXISTING_CGROUP_RULES" == *"c $LIVE_METIS_MAJOR:* rmw"* ]] || STALE_DEVICES+=("metis (current major $LIVE_METIS_MAJOR)")
    fi
    if [[ -e /dev/dma_heap/system ]]; then
      LIVE_DMAHEAP_MAJOR=$((16#$(stat -c '%t' /dev/dma_heap/system)))
      [[ "$EXISTING_CGROUP_RULES" == *"c $LIVE_DMAHEAP_MAJOR:* rmw"* ]] || STALE_DEVICES+=("dma_heap (current major $LIVE_DMAHEAP_MAJOR)")
    fi
    if [[ "$HOST_OPENCL_AVAILABLE" == "1" ]]; then
      SAMPLE_DRI_DEV="$(ls /dev/dri/render* 2>/dev/null | head -1 || true)"
      if [[ -n "$SAMPLE_DRI_DEV" ]]; then
        LIVE_DRI_MAJOR=$((16#$(stat -c '%t' "$SAMPLE_DRI_DEV")))
        [[ "$EXISTING_CGROUP_RULES" == *"c $LIVE_DRI_MAJOR:* rmw"* ]] || STALE_DEVICES+=("dri render node (current major $LIVE_DRI_MAJOR)")
      fi
    fi
    if [[ ${#STALE_DEVICES[@]} -gt 0 ]]; then
      {
        echo "ERROR: $CONTAINER_NAME's device-cgroup-rule no longer matches this host's"
        echo "live device major number(s) for: ${STALE_DEVICES[*]}."
        echo "This container will see but fail to open the affected device(s) at runtime"
        echo "(\"Operation not permitted\"), most often after a kernel driver reload or"
        echo "host reboot changed the dynamically-assigned major. Fix: re-run this exact"
        echo "setup.sh command with --force-recreate-container to rebuild it with the"
        echo "current major number(s)."
      } >&2
      exit 1
    fi
    log "PHASE: ensure_container PASS (reusing existing $CONTAINER_NAME, device-cgroup-rule majors still valid)"
  fi

  DOCKER_ARGS=(--target host --sdk-repo-url "$SDK_REPO_URL" \
               --sdk-dest-dir "$SDK_DEST_DIR" --sdk-ref "$SDK_REF" \
               --project-dir "$PROJECT_DIR")
  [[ "$FORCE_REINSTALL_SDK" == "1" ]] && DOCKER_ARGS+=(--force-reinstall-sdk)
  [[ "$FORCE_REBUILD_SERVER" == "1" ]] && DOCKER_ARGS+=(--force-rebuild-server)
  [[ -n "$MODEL_CONFIG" ]] && DOCKER_ARGS+=(--model-config "$MODEL_CONFIG")
  [[ -n "$DEPLOY_ARGS" ]] && DOCKER_ARGS+=(--deploy-args "$DEPLOY_ARGS")
  [[ "$SKIP_COMPILE" == "1" ]] && DOCKER_ARGS+=(--skip-compile)
  [[ "$SKIP_SMOKETEST" == "1" ]] && DOCKER_ARGS+=(--skip-smoketest)
  [[ -n "$SMOKE_ENDPOINTS" ]] && DOCKER_ARGS+=(--smoke-endpoints "$SMOKE_ENDPOINTS")
  [[ -n "$SMOKE_IMAGE" ]] && DOCKER_ARGS+=(--smoke-image "$SMOKE_IMAGE")
  DOCKER_ARGS+=(--smoke-batch-size "$SMOKE_BATCH_SIZE")
  if [[ -n "$PLACE_YAML_SRC" ]]; then
    DOCKER_ARGS+=(--place-yaml "$PLACE_YAML_SRC" "$PLACE_YAML_DEST")
  fi
  [[ "$MONITOR" == "1" ]] && DOCKER_ARGS+=(--monitor)
  [[ "$VLLM_AXPLUGIN" == "1" ]] && DOCKER_ARGS+=(--vllm-axplugin)
  DOCKER_EXEC_ENV_ARGS=(-e SETUP_INSIDE_DOCKER_DISPATCH=1 -e "SETUP_HOST_OPENCL_AVAILABLE=$HOST_OPENCL_AVAILABLE")
  if [[ "$INTERNAL_SDK" == "1" ]]; then
    DOCKER_ARGS+=(--internal-sdk)
    for v in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN; do
      [[ -n "${!v:-}" ]] && DOCKER_EXEC_ENV_ARGS+=(-e "$v=${!v}")
    done
  fi

  log "PHASE: dispatch_to_container ($CONTAINER_NAME)"
  exec docker exec "${DOCKER_EXEC_ENV_ARGS[@]}" "$CONTAINER_NAME" bash "$SCRIPT_PATH" "${DOCKER_ARGS[@]}"
fi

if [[ "$TARGET" != "host" ]]; then
  echo "ERROR: --target must be 'host' or 'docker', got: $TARGET" >&2
  exit 2
fi

if [[ -n "$PLACE_YAML_SRC" ]]; then
  mkdir -p "$PLACE_YAML_DEST"
  cp "$PLACE_YAML_SRC" "$PLACE_YAML_DEST/"
  log "PHASE: place_yaml PASS ($PLACE_YAML_DEST/$(basename "$PLACE_YAML_SRC"))"
  if [[ -z "$SDK_REPO_URL" ]]; then
    exit 0
  fi
fi

if [[ -z "$SDK_REPO_URL" || -z "$SDK_DEST_DIR" || -z "$SDK_REF" ]]; then
  echo "ERROR: --sdk-repo-url, --sdk-dest-dir, and --sdk-ref are required for host setup" >&2
  exit 2
fi

SETUP_MARKER="$SDK_DEST_DIR/.axelera_setup_complete"

if [[ "$FORCE_REINSTALL_SDK" == "1" && -e "$SDK_DEST_DIR" ]]; then
  log "PHASE: clone_checkout (--force-reinstall-sdk: removing existing $SDK_DEST_DIR)"
  rm -rf "$SDK_DEST_DIR"
fi

if [[ -d "$SDK_DEST_DIR/.git" ]]; then
  log "PHASE: clone_checkout (existing repo, fetching $SDK_REF)"
  git -C "$SDK_DEST_DIR" fetch --depth 1 origin "$SDK_REF"
  git -C "$SDK_DEST_DIR" checkout --detach FETCH_HEAD
else
  mkdir -p "$(dirname "$SDK_DEST_DIR")"
  log "PHASE: clone_checkout (fresh clone)"
  if git clone --filter=blob:none --no-checkout "$SDK_REPO_URL" "$SDK_DEST_DIR" 2>/dev/null \
     && git -C "$SDK_DEST_DIR" fetch --depth 1 origin "$SDK_REF" \
     && git -C "$SDK_DEST_DIR" checkout --detach FETCH_HEAD; then
    :
  else
    log "shallow fetch of ref '$SDK_REF' failed, falling back to full clone"
    rm -rf "$SDK_DEST_DIR"
    git clone "$SDK_REPO_URL" "$SDK_DEST_DIR"
    git -C "$SDK_DEST_DIR" checkout "$SDK_REF"
  fi
fi
RESOLVED_SHA="$(git -C "$SDK_DEST_DIR" rev-parse HEAD)"
log "PHASE: clone_checkout PASS (HEAD=$RESOLVED_SHA)"

INTERNAL_SDK_CA_CERT="/usr/local/share/ca-certificates/aws-axelera-ai-ca.crt"
NEEDS_INSTALL=0
if [[ ! -f "$SETUP_MARKER" ]] && { [[ -x "$SDK_DEST_DIR/install.sh" ]] || [[ -x "$SDK_DEST_DIR/install-dependencies.sh" ]]; }; then
  NEEDS_INSTALL=1
fi
if [[ "$INTERNAL_SDK" == "1" && ! -f "$INTERNAL_SDK_CA_CERT" ]]; then
  NEEDS_INSTALL=1
fi
if [[ "$NEEDS_INSTALL" == "1" && "$EUID" != "0" ]] && ! sudo -n true 2>/dev/null; then
  if [[ -n "${SETUP_SUDO_PASSWORD:-}" ]]; then
    log "PHASE: sudo_preflight (priming sudo credential from SETUP_SUDO_PASSWORD)"
    if ! printf '%s\n' "$SETUP_SUDO_PASSWORD" | sudo -S -p '' true; then
      echo "ERROR: sudo authentication failed with the supplied SETUP_SUDO_PASSWORD" >&2
      exit 1
    fi
    unset SETUP_SUDO_PASSWORD
    log "PHASE: sudo_preflight PASS"
  else
    {
      echo "ERROR: install_deps needs sudo (for apt packages) but this session has no"
      echo "cached sudo credential and no password was supplied. Do ONE of:"
      echo ""
      echo "  1) Run this exact command yourself, interactively (you'll be prompted):"
      echo "       sudo bash \"$SCRIPT_PATH\" ${ORIGINAL_ARGS[*]}"
      echo ""
      echo "  2) Re-run with your sudo password available non-interactively (never put"
      echo "     the password on the command line, in a file, or in a commit):"
      echo "       SETUP_SUDO_PASSWORD='<your password>' bash \"$SCRIPT_PATH\" ${ORIGINAL_ARGS[*]}"
      echo ""
      echo "  3) Configure passwordless sudo for apt-get on this host once, then re-run"
      echo "     with no password needed at all."
    } >&2
    exit 1
  fi
fi

if [[ "$INTERNAL_SDK" == "1" ]]; then
  if [[ -f "$INTERNAL_SDK_CA_CERT" ]]; then
    log "PHASE: internal_sdk_ca SKIP (already trusted: $INTERNAL_SDK_CA_CERT)"
  else
    MISSING_AWS_VARS=()
    for v in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
      [[ -z "${!v:-}" ]] && MISSING_AWS_VARS+=("$v")
    done
    if [[ ${#MISSING_AWS_VARS[@]} -gt 0 ]]; then
      {
        echo "ERROR: --internal-sdk needs AWS credentials to fetch the internal CA cert,"
        echo "but these are missing from the environment: ${MISSING_AWS_VARS[*]}"
        echo ""
        echo "Internal SDK releases need ONLY SETUP_SUDO_PASSWORD (if applicable) plus"
        echo "AWS credentials -- nothing else manual. Export them yourself (never put them"
        echo "on the command line, in a file, or in a commit) and re-run:"
        echo "       AWS_ACCESS_KEY_ID='...' AWS_SECRET_ACCESS_KEY='...' \\"
        echo "       [AWS_SESSION_TOKEN='...'] bash \"$SCRIPT_PATH\" ${ORIGINAL_ARGS[*]}"
      } >&2
      exit 1
    fi
    SUDO_CMD=()
    [[ "$EUID" != "0" ]] && SUDO_CMD=(sudo)
    log "PHASE: internal_sdk_ca (fetching CA cert)"
    if ! command -v aws >/dev/null 2>&1; then
      "${SUDO_CMD[@]}" apt-get update -qq
      "${SUDO_CMD[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -qq -y awscli >/dev/null
    fi
    TMP_CA_CERT="$(mktemp)"
    aws s3 cp s3://axelera-sw-ci-inputs/ca-certificates/aws-axelera-ai-ca.crt "$TMP_CA_CERT"
    "${SUDO_CMD[@]}" mv "$TMP_CA_CERT" "$INTERNAL_SDK_CA_CERT"
    "${SUDO_CMD[@]}" update-ca-certificates
    log "PHASE: internal_sdk_ca PASS"
  fi
fi

if [[ -f "$SETUP_MARKER" ]]; then
  # Reusing an existing install: still ensure OS prerequisites and refresh dependencies.
  _preseed_tzdata_noninteractive
  _ensure_pciutils
  _ensure_numactl
  [[ "${SETUP_HOST_OPENCL_AVAILABLE:-0}" == "1" ]] && _ensure_opencl_runtime
  if [[ -x "$SDK_DEST_DIR/install-dependencies.sh" ]]; then
    pushd "$SDK_DEST_DIR" >/dev/null
    ./install-dependencies.sh >/dev/null 2>&1 || true
    popd >/dev/null
  else
    _ensure_server_build_tools
    _ensure_gobject_introspection
  fi
  log "PHASE: install_deps SKIP (reusing existing install, marker found: $SETUP_MARKER; use --force-reinstall-sdk to redo)"
elif [[ -x "$SDK_DEST_DIR/install.sh" ]]; then
  log "PHASE: install_deps (install.sh)"
  INSTALL_SH_EXTRA_ARGS=()
  if [[ "$EUID" == "0" ]]; then
    INSTALL_SH_EXTRA_ARGS+=(--allow-as-sudo)
  fi
  _preseed_tzdata_noninteractive
  _ensure_pciutils
  _ensure_numactl
  _ensure_server_build_tools
  _ensure_gobject_introspection
  [[ "${SETUP_HOST_OPENCL_AVAILABLE:-0}" == "1" ]] && _ensure_opencl_runtime
  pushd "$SDK_DEST_DIR" >/dev/null
  ./install.sh --development --runtime --no-driver --YES "${INSTALL_SH_EXTRA_ARGS[@]}"
  popd >/dev/null
  touch "$SETUP_MARKER"
  log "PHASE: install_deps PASS"
elif [[ -x "$SDK_DEST_DIR/install-dependencies.sh" ]]; then
  log "PHASE: install_deps (install-dependencies.sh + pip)"
  _preseed_tzdata_noninteractive
  _ensure_pciutils
  _ensure_numactl
  _ensure_server_build_tools
  _ensure_gobject_introspection
  [[ "${SETUP_HOST_OPENCL_AVAILABLE:-0}" == "1" ]] && _ensure_opencl_runtime
  pushd "$SDK_DEST_DIR" >/dev/null
  ./install-dependencies.sh
  SDK_VERSION="$(cat VERSION.TXT 2>/dev/null || true)"
  if [[ -x "venv/bin/axversion" && "$(venv/bin/axversion 2>/dev/null)" == "$SDK_VERSION" ]]; then
    log "PHASE: install_deps (venv already at $SDK_VERSION, skipping pip install)"
  else
    test -d venv || python3 -m venv venv
    source venv/bin/activate
    pip install -q --upgrade pip
    PIP_SPEC=(axelera-rt "axelera-devkit[all]")
    [[ -n "$SDK_VERSION" ]] && PIP_SPEC=("axelera-rt==$SDK_VERSION" "axelera-devkit[all]==$SDK_VERSION")
    pip install --extra-index-url https://software.axelera.ai/artifactory/api/pypi/axelera-pypi/simple "${PIP_SPEC[@]}"
    make operators
    deactivate
    [[ -z "$SDK_VERSION" || "$(venv/bin/axversion)" == "$SDK_VERSION" ]] || { echo "ERROR: axversion after pip install ($(venv/bin/axversion)) does not match VERSION.TXT ($SDK_VERSION)" >&2; exit 1; }
  fi
  venv/bin/pip install -q 'transformers==4.57.6'
  popd >/dev/null
  touch "$SETUP_MARKER"
  log "PHASE: install_deps PASS"
else
  log "PHASE: install_deps SKIP (no install.sh/install-dependencies.sh found in $SDK_DEST_DIR)"
fi

# Build the gRPC server against the SDK venv.
SERVER_DIR="$PROJECT_DIR/server"
SERVER_BIN="$SERVER_DIR/build/axinferencenet_grpc"
if [[ ! -f "$SERVER_DIR/CMakeLists.txt" ]]; then
  log "PHASE: server_build SKIP (no server/CMakeLists.txt found in $PROJECT_DIR)"
elif [[ ! -x "$SDK_DEST_DIR/venv/bin/python3" ]]; then
  log "PHASE: server_build SKIP (no SDK venv at $SDK_DEST_DIR/venv to build against)"
else
  # Check whether the existing server binary has unresolved shared libraries.
  #
  # Runs ldd with the SDK venv activated and operators/lib on LD_LIBRARY_PATH.
  #
  # Globals:
  #   SERVER_BIN, SDK_DEST_DIR (string): read.
  #
  # Returns:
  #   0: The binary exists and ldd reports a missing library.
  #   1: Otherwise.
  _server_libs_stale() {
    [[ -x "$SERVER_BIN" ]] || return 1
    local missing
    missing="$(bash -c "source \"$SDK_DEST_DIR/venv/bin/activate\" && export LD_LIBRARY_PATH=\"$SDK_DEST_DIR/operators/lib:\${LD_LIBRARY_PATH:-}\" && ldd \"$SERVER_BIN\"" 2>/dev/null | grep -i 'not found' || true)"
    [[ -n "$missing" ]]
  }
  CLEAN_BUILD=0
  if [[ "$FORCE_REBUILD_SERVER" == "1" ]]; then
    REBUILD_REASON="--force-rebuild-server: full clean rebuild"
    CLEAN_BUILD=1
  elif [[ ! -x "$SERVER_BIN" ]]; then
    REBUILD_REASON="binary missing: full build"
    CLEAN_BUILD=1
  elif _server_libs_stale; then
    REBUILD_REASON="shared libraries unresolved (OS packages drifted under an existing binary): full clean rebuild"
    CLEAN_BUILD=1
  else
    REBUILD_REASON="binary present and libs resolve: incremental cmake/ninja (picks up source changes, if any)"
  fi
  log "PHASE: server_build ($REBUILD_REASON)"
  _ensure_server_build_tools
  PYVER="$("$SDK_DEST_DIR/venv/bin/python3" -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
  export PKG_CONFIG_PATH="$SDK_DEST_DIR/operators/lib/pkgconfig:$SDK_DEST_DIR/venv/lib/$PYVER/site-packages/axelera/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
  export USE_SIMD_DECODE=1
  [[ "$CLEAN_BUILD" == "1" ]] && rm -rf "$SERVER_DIR/build"
  pushd "$SERVER_DIR" >/dev/null
  cmake -B build -GNinja
  cmake --build build
  popd >/dev/null
  if [[ -x "$SERVER_BIN" ]]; then
    log "PHASE: server_build PASS"
  else
    echo "ERROR: server build did not produce $SERVER_BIN" >&2
    exit 1
  fi
fi

if [[ "${SETUP_INSIDE_DOCKER_DISPATCH:-0}" != "1" ]]; then
  log "PHASE: host_server_setup SKIP (--target host, not a docker dispatch)"
else
  DEPLOYMENT_DIR="$PROJECT_DIR/deployment"
  if [[ ! -f "$DEPLOYMENT_DIR/host_server.py" ]]; then
    log "PHASE: host_server_setup SKIP (no host_server.py found at $DEPLOYMENT_DIR)"
  else
    if [[ -x "$DEPLOYMENT_DIR/venv/bin/uvicorn" ]]; then
      log "PHASE: host_server_setup (venv already at $DEPLOYMENT_DIR/venv, skipping pip install)"
    else
      log "PHASE: host_server_setup (creating dedicated venv at $DEPLOYMENT_DIR/venv)"
      python3 -m venv "$DEPLOYMENT_DIR/venv"
      "$DEPLOYMENT_DIR/venv/bin/pip" install -q --upgrade pip
      "$DEPLOYMENT_DIR/venv/bin/pip" install -q -e "$DEPLOYMENT_DIR"
    fi

    HOST_SERVER_ENV="$DEPLOYMENT_DIR/.env"
    if [[ -f "$HOST_SERVER_ENV" ]]; then
      log "PHASE: host_server_setup ($HOST_SERVER_ENV already exists, reusing)"
    else
      log "PHASE: host_server_setup (generating $HOST_SERVER_ENV)"
      GENERATED_API_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
      cat > "$HOST_SERVER_ENV" <<ENVEOF
DEPLOYMENT_API_KEY=$GENERATED_API_KEY
BIND_HOST=0.0.0.0
BIND_PORT=8088
SETUP_SCRIPT_PATH=$SCRIPT_PATH
YAML_UPLOAD_DIR=$DEPLOYMENT_DIR/uploaded_yaml
SDK_ROOT=$SDK_DEST_DIR
ALLOWED_SDK_DEST_PREFIXES=$(dirname "$SDK_DEST_DIR")
ENVEOF
      chmod 600 "$HOST_SERVER_ENV"
    fi

    if curl -sf -o /dev/null "http://127.0.0.1:8088/api/v1/health" 2>/dev/null; then
      log "PHASE: host_server_setup PASS (already running at http://0.0.0.0:8088)"
    else
      log "PHASE: host_server_setup (launching uvicorn host_server:app)"
      pushd "$DEPLOYMENT_DIR" >/dev/null
      nohup "$DEPLOYMENT_DIR/venv/bin/uvicorn" host_server:app \
        --host 0.0.0.0 --port 8088 > host_server_live.log 2>&1 &
      disown
      popd >/dev/null
      HOST_SERVER_UP=0
      for i in $(seq 1 20); do
        if curl -sf -o /dev/null "http://127.0.0.1:8088/api/v1/health" 2>/dev/null; then
          HOST_SERVER_UP=1
          break
        fi
        sleep 1
      done
      if [[ "$HOST_SERVER_UP" != "1" ]]; then
        echo "ERROR: host_server.py did not come up, log:" >&2
        cat "$DEPLOYMENT_DIR/host_server_live.log" >&2
        exit 1
      fi
      log "PHASE: host_server_setup PASS (launched at http://0.0.0.0:8088, API key in $HOST_SERVER_ENV)"
    fi
  fi
fi

if [[ "${SETUP_INSIDE_DOCKER_DISPATCH:-0}" != "1" || "$MONITOR" != "1" ]]; then
  log "PHASE: monitor_setup SKIP (--monitor not set, or not a docker dispatch)"
else
  MONITOR_SETUP_SCRIPT="$PROJECT_DIR/deployment/monitor/setup.sh"
  if [[ ! -f "$MONITOR_SETUP_SCRIPT" ]]; then
    log "PHASE: monitor_setup SKIP (no setup.sh found at $MONITOR_SETUP_SCRIPT)"
  else
    log "PHASE: monitor_setup"
    SDK_ROOT="$SDK_DEST_DIR" bash "$MONITOR_SETUP_SCRIPT"
    log "PHASE: monitor_setup PASS"
  fi
fi

if [[ "${SETUP_INSIDE_DOCKER_DISPATCH:-0}" != "1" || "$VLLM_AXPLUGIN" != "1" ]]; then
  log "PHASE: vllm_axplugin_setup SKIP (--vllm-axplugin not set, or not a docker dispatch)"
else
  VENV_VLLM_DIR="$PROJECT_DIR/.venv-vllm"
  AXPLUGIN_DIR="$PROJECT_DIR/server/vllm/axelera"
  SDK_PY="$SDK_DEST_DIR/venv/bin/python3"
  if [[ ! -d "$AXPLUGIN_DIR" ]]; then
    log "PHASE: vllm_axplugin_setup SKIP (no axplugin found at $AXPLUGIN_DIR)"
  else
    if [[ -e "$VENV_VLLM_DIR" ]] && ! "$VENV_VLLM_DIR/bin/python3" -c 'import torch, vllm' >/dev/null 2>&1; then
      log "PHASE: vllm_axplugin_setup (.venv-vllm at $VENV_VLLM_DIR is incomplete -- torch/vllm not importable; deleting it to start fresh)"
      rm -rf "$VENV_VLLM_DIR"
    fi
    if [[ -x "$VENV_VLLM_DIR/bin/python3" ]]; then
      log "PHASE: vllm_axplugin_setup (.venv-vllm already at $VENV_VLLM_DIR, skipping torch/vllm install)"
    else
      log "PHASE: vllm_axplugin_setup (creating $VENV_VLLM_DIR with --system-site-packages)"
      "$SDK_PY" -m venv --system-site-packages "$VENV_VLLM_DIR"

      if [[ -w /etc/gai.conf ]] && ! grep -qE '^precedence\s+::ffff:0:0/96' /etc/gai.conf; then
        echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf
      fi

      if ! "$VENV_VLLM_DIR/bin/pip" install -q --index-url https://download.pytorch.org/whl/cpu \
        'torch==2.11.0+cpu' 'torchvision==0.26.0+cpu' 'torchaudio==2.11.0+cpu'; then
        log "PHASE: vllm_axplugin_setup (torch install failed, retrying with IPv4-only DNS resolution)"
        "$VENV_VLLM_DIR/bin/python3" -c "
import sys
import pip._vendor.urllib3.util.connection as nc
nc.HAS_IPV6 = False
import pip._internal.cli.main as pip_cli
sys.exit(pip_cli.main(['install', '-q', '--index-url', 'https://download.pytorch.org/whl/cpu',
                        'torch==2.11.0+cpu', 'torchvision==0.26.0+cpu', 'torchaudio==2.11.0+cpu']))
"
      fi
      "$VENV_VLLM_DIR/bin/pip" install -q 'vllm @ https://github.com/vllm-project/vllm/releases/download/v0.26.0/vllm-0.26.0+cpu-cp38-abi3-manylinux_2_34_x86_64.whl'
      "$VENV_VLLM_DIR/bin/pip" install -q 'transformers==5.20.2'
      "$VENV_VLLM_DIR/bin/pip" uninstall -y -q torchcodec || true
      SDK_SITE=$("$SDK_PY" -c 'import site; print(site.getsitepackages()[0])')
      VENV_SITE=$("$VENV_VLLM_DIR/bin/python3" -c 'import site; print(site.getsitepackages()[0])')
      echo "$SDK_SITE" > "$VENV_SITE/sdk_axelera.pth"
    fi

    log "PHASE: vllm_axplugin_setup (installing axplugin from $AXPLUGIN_DIR)"
    "$VENV_VLLM_DIR/bin/pip" install -q -e "$AXPLUGIN_DIR" --no-deps --no-build-isolation

    PLATFORM_TYPE=$("$VENV_VLLM_DIR/bin/python3" -c 'from vllm.platforms import current_platform; print(type(current_platform).__name__)' | tail -n1)
    if [[ "$PLATFORM_TYPE" != "AxeleraPlatform" ]]; then
      echo "ERROR: vllm did not discover axplugin (current_platform is $PLATFORM_TYPE, expected AxeleraPlatform)" >&2
      exit 1
    fi
    log "PHASE: vllm_axplugin_setup PASS (.venv-vllm at $VENV_VLLM_DIR, axplugin installed and discovered)"

    HUGGINGFACE_PY="$SDK_DEST_DIR/model_axscript/llm/huggingface.py"
    if [[ ! -f "$HUGGINGFACE_PY" ]]; then
      log "PHASE: vllm_axplugin_setup SKIP axcausallm patches (no $HUGGINGFACE_PY in this SDK checkout)"
    else
      for PATCH in patch_axcausallm_rope_config.py patch_axcausallm_cache_position.py; do
        PATCH_SCRIPT="$PROJECT_DIR/server/patches/$PATCH"
        log "PHASE: vllm_axplugin_setup (applying $PATCH to $HUGGINGFACE_PY)"
        "$SDK_PY" "$PATCH_SCRIPT" "$HUGGINGFACE_PY"
      done
      log "PHASE: vllm_axplugin_setup PASS (axcausallm patches applied to $HUGGINGFACE_PY)"
    fi
  fi
fi

if [[ "$SKIP_COMPILE" == "1" ]]; then
  log "PHASE: compile_models SKIP (--skip-compile)"
elif [[ -z "$MODEL_CONFIG" ]]; then
  log "PHASE: compile_models SKIP (no --model-config given)"
else
  DEPLOY_PY="$SDK_DEST_DIR/deploy.py"
  if [[ ! -f "$DEPLOY_PY" ]]; then
    echo "ERROR: deploy.py not found at $DEPLOY_PY" >&2
    exit 1
  fi
  log "PHASE: compile_models (deploy.py $MODEL_CONFIG $DEPLOY_ARGS)"
  (cd "$SDK_DEST_DIR" && source venv/bin/activate 2>/dev/null || true
   python3 deploy.py "$MODEL_CONFIG" $DEPLOY_ARGS)
  log "PHASE: compile_models PASS"
fi

# Endpoint smoke tests are not part of setup.sh; the --skip-smoketest, --smoke-*
# flags are accepted for compatibility and ignored.
log "PHASE: smoke_test SKIP (disabled -- not setup.sh's job; see comment above)"

log "setup.sh: ALL PHASES PASS (HEAD=$RESOLVED_SHA)"
