# Helper agent

A ready-to-run [Claude Code](https://claude.com/claude-code) project that
drives the Pipeline Editor GUI for you: you describe the pipeline or benchmark
you want, and it builds, launches and benchmarks it through the GUI's MCP
server. Everything it needs lives in [`agent/`](agent/).

## How it fits together

- **The skill** — [`inference-server-agent`](agent/.claude/skills/inference-server-agent/SKILL.md)
  is the agent's main interface. Claude Code loads it automatically from
  `agent/`.
- **The MCP server** — the skill sends Claude to the `pipeline-editor-gui` MCP
  server ([`agent/.mcp.json`](agent/.mcp.json), served by
  `client/ui/gui/agent_mcp_server.py`), which is the agent's only way to see
  and change the GUI. Tool contracts: [`../gui/mcp-endpoints.md`](../gui/mcp-endpoints.md).
- **The runbooks** — the skill then follows the call-by-call runbooks indexed
  at [`agent/runbook/index.md`](agent/runbook/index.md) (vision, VLM/LLM,
  cascades, benchmarking, performance tuning, YAML save/modify/load).

## Setup

Complete these steps first:

1. Start the GUI ([`../../QUICKSTART.md`](../../QUICKSTART.md) sections 1–2).
2. Install the agent tools. `client/setup.sh --agent` does this. It installs Node through nvm and the Claude Code CLI.

Then prepare the shell:

```bash
source ~/.nvm/nvm.sh                    # puts claude on the PATH of a new shell
cd client/docs/helper/agent
export GUI_APP_PORT=8080                # the port of your GUI (default 8080)
export ANTHROPIC_API_KEY="sk-ant-..."   # your own key
```

The agent needs your GUI's client id. The GUI shows it. You can also list the ids of the open GUI tabs. A tab must
be open, otherwise the list is empty:

```bash
curl -s http://127.0.0.1:$GUI_APP_PORT/_agent/sessions
```

Start the CLI:

```bash
claude --model claude-haiku-5-5 --autocompact 500k --allowedTools "mcp__pipeline-editor-gui"
```

`claude mcp list` shows `pipeline-editor-gui` as "Pending approval" until you approve it once in an interactive
`claude` session. A headless run (`claude -p`) works without that approval.

## Why Haiku with a 500k context

The skill, the MCP server and the runbooks carry the detail. The agent needs no large or especially capable model
to do almost everything the GUI can do. We recommend Claude Haiku 5.5 with the context window capped at 500k
(`--autocompact 500k`).

## Permissions

Claude Code asks before it runs a tool. We recommend that you allow only the GUI's MCP tools:

```bash
claude --model claude-haiku-5-5 --autocompact 500k --allowedTools "mcp__pipeline-editor-gui"
```

The agent can then drive the whole GUI without prompts and without any other permission. We ran a complete
detection pipeline and benchmark this way. The agent may try other tools, such as `find` over the work tree. Claude
Code blocks those calls, and the agent carries on.

`--dangerously-skip-permissions` also works. It removes every permission check, so Claude can run any tool without
asking. We found the skill safe under it, but the flag does not suit every user or environment. Use
`--allowedTools` unless you have a reason not to.

## Run without the terminal UI

Pass the prompt with `-p` to run the agent headless and read its answer on stdout:

```bash
claude -p --model claude-haiku-5-5 --autocompact 500k --allowedTools "mcp__pipeline-editor-gui" "/goal ..."
```

## Example prompts

Start each prompt with **`/goal`**. It is the recommended way to prompt the
helper agent: **`/goal`** sets the outcome the agent keeps working toward
until it is reached (here, a successful benchmark), instead of stopping after
a single reply. Paste your GUI's client id where shown (it is displayed in the
GUI).

```
/goal Can you please help me build a single object detection pipeline with yolox-m-coco onnx model?
follow the inference-server-agent skill verbatim for best practices, keep going until we have a successful benchmark with yolox-m-coco onnx model.
My GUI's client-id is: <paste-client-id-from-the-GUI>
```

```
/goal Can you please help me build an object detection based pipeline with which I can stress test my server/host; we can use yolox-m-coco onnx model?
follow the inference-server-agent skill verbatim for best practices, keep going until we have a successful benchmark results.
My GUI's client-id is: <paste-client-id-from-the-GUI>
```

```
/goal Can you please help me build a simple VLM demo pipeline with smolVLMv2 instruct model?
follow the inference-server-agent skill verbatim for best practices, keep going until we have a successful benchmark with smolVLMv2 instruct model.
My GUI's client-id is: <paste-client-id-from-the-GUI>
```
