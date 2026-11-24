#!/bin/bash
#
# Check that Node and the Claude Code CLI are installed, installing them when missing.
#
# USAGE:
#   ./setup.sh
#
# DEPENDENCIES:
#   - curl, bash (nvm installer, used only if node is missing)
#   - nvm / npm (Node 24 and the global @anthropic-ai/claude-code package)
#
# ENV VARIABLES:
#   NVM_DIR (path): nvm installation directory. Required: No. Default: $HOME/.nvm.
#
# EXIT CODES:
#   0: Success.
#   other: A failing command under set -e (for example a failed install).
#
# EXAMPLE:
#   ./setup.sh
set -euo pipefail

# Print a message prefixed with the script path.
#
# Arguments:
#   $@ (string): Message text.
#
# Outputs:
#   stdout: "[docs/helper/agent/setup.sh] <message>".
#
# Returns:
#   0: Success.
log() { echo "[docs/helper/agent/setup.sh] $*"; }

if ! command -v node >/dev/null 2>&1; then
  log "PHASE: node (not found, installing Node 24 via nvm)"
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm install 24
fi
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  . "$NVM_DIR/nvm.sh"
fi
log "PHASE: node PASS ($(node --version))"

if ! command -v claude >/dev/null 2>&1; then
  log "PHASE: claude_code (not found, installing @anthropic-ai/claude-code)"
  npm install -g @anthropic-ai/claude-code
fi
log "PHASE: claude_code PASS ($(claude --version))"

log "All checks passed. Next: cd $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd) && claude --model claude-haiku-5-5 --autocompact 500k  (see docs/helper/README.md for the full setup, permissions note and example prompts)"
log "Then inside the session, ask to list MCP tools -- the GUI's tools (list_sessions, get_state, click, ...) should appear automatically via .mcp.json."
log "NOTE: .mcp.json points at http://127.0.0.1:\${GUI_APP_PORT:-8080} -- if app.py was launched with a non-default GUI_APP_PORT, export that same GUI_APP_PORT in this shell before running claude, or the MCP server will talk to the wrong port."
