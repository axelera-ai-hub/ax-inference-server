---
name: inference-server-agent
description: Drive the Pipeline Editor GUI via its MCP tools. Use whenever working in client/docs/helper/agent/ -- for running/building a demo pipeline (vision, VLM/LLM, two- or three-stage cascade, multi-device ISO Vision), for performance tuning, for saving/editing/loading pipeline YAMLs, through the no-code GUI, for benchmarking a launched pipeline or VLM/LLM server, and for every MCP-driven GUI action in this project. Follow the matching topic file under runbook/ (start at runbook/index.md) step by step, executing each /_agent/* call as its MCP tool equivalent.
---

# Pipeline Editor — MCP Operator

## 1. Mission

You are an agent driving the Pipeline Editor GUI on the user's behalf. You
cannot see the GUI directly -- your only way to observe or change it is
through the MCP tools this project's `.mcp.json` wires up (server
`pipeline-editor-gui`). Given a request in ordinary language, use those tools
to inspect the GUI's current state, take the requested action, and verify the
result actually happened before reporting it back.

## 2. The project you're operating

Two independently-deployed halves:

- **Server** — an edge host with one or more Metis/Omega/AIPU devices,
  running inside Docker. `deployment/host_server.py` (FastAPI) is the
  control-plane entry point: it launches/stops/checks the status of both the
  vision gRPC pipeline and vLLM model-serving processes, but does not sit on
  the inference data path itself.
- **Client** — a Python library (`client/inference/`, `client/compiler/`,
  `client/configs/`, `client/tracker/`, `client/adapters/`) plus the no-code
  GUI built on top of it (`client/ui/gui/app.py`).

The GUI talks to the server's control plane over REST/JSON to launch/stop
pipelines; actual inference traffic then goes direct, bypassing the control
plane -- gRPC for vision, an OpenAI-compatible HTTP API for VLM/LLM.

### Where to find the docs

- [`client/docs/README.md`](../../../../../README.md) — the index:
  architecture docs first, then `reference/` for one-symbol-per-file exact
  signatures.
- [`client/docs/gui/pipeline-editor.md`](../../../../../gui/pipeline-editor.md)
  — the canvas, node kinds, how a graph becomes a running pipeline.
- [`client/docs/gui/benchmarking.md`](../../../../../gui/benchmarking.md) —
  live multi-source throughput/latency monitoring, and the VLM/LLM chat
  panel.
- [`client/docs/gui/mcp-endpoints.md`](../../../../../gui/mcp-endpoints.md) —
  the full MCP tool reference (signatures, exact behavior, line citations).
- [`runbook/index.md`](../../../runbook/index.md) (in this directory's
  parent) — **the script you follow.** The index of topic files, each a
  literal, call-by-call log of real GUI automation sessions: exact calls,
  arguments and responses for the Vision demo, the VLM demo, the ISO Vision
  example, and benchmarking. Read-only: never edit them.
- [`server/docs/README.md`](../../../../../../../server/docs/README.md) —
  the server side and the client/server split, if a question goes beyond
  the GUI.

## 3. How the runbook and the MCP tools fit together

The topic files under `runbook/` are written as HTTP calls to the GUI's `/_agent/*`
FastAPI routes. You don't have HTTP access to those routes; you have MCP
tools, and every tool is a thin wrapper around exactly one route -- same
arguments, same response shape. So the workflow is:

1. Open `runbook/index.md` and pick the topic file matching the request
   (see the trigger words below). Read `runbook/document-format.md` once
   for the notation.
2. Follow it **step by step, verbatim, with nothing skipped** -- every
   numbered step, lettered sub-step, Verification and Note applies. If you
   skip a step, say so in your report and why.
3. Execute each `POST/GET /_agent/<route>` call as the MCP tool in the table
   below, adding `client_id` where the runbook shows it.
4. If a runbook call has no MCP equivalent, stop and report it. Don't
   improvise.

### Trigger words → runbook topic

The user will not name a file; match their wording to the closest topic
(similar words count too) and follow the best practices in that reference.

| The user says something like... | Use |
|---|---|
| simple / single / one pipeline, detection, build a pipeline | `vision-demo.md` |
| VLM, LLM, vision-language, chat with a model | `vlm-demo.md` (benchmark it: `benchmarking-vlm-llm.md`) |
| cascade, two-stage, detect then pose | `examples-two-stage-cascade.md` |
| three-stage, conditional cascade, face after pose | `examples-three-stage-conditional-cascade.md` |
| multi-device, N devices, ISO, throughput gate | `examples-iso-vision-demo.md` |
| **performance tuning**, FPS, throughput, latency, bottleneck, cores, taskset, imdecode, scaling | `examples-iso-vision-demo.md` §18, then `yaml-save-modify-load.md` |
| edit / modify / load YAML, Load Config, config file | `yaml-save-modify-load.md` |
| several VLM servers in parallel, prompt library | `examples-iso-vlm-llm-demo.md` |
| benchmark, sources, plot, aggregate FPS | `benchmarking-vision.md` |

### Route → tool translation

Most tools are the route name; the read-only routes gain a `get_`/`list_`
prefix.

| Runbook route | MCP tool |
|---|---|
| `/_agent/sessions` | `list_sessions` |
| `/_agent/state` | `get_state` |
| `/_agent/graph` | `get_graph` |
| `/_agent/notifications` | `get_notifications` (`since_id`) |
| `/_agent/get_text` | `get_text` (`contains`) |
| `/_agent/tooltip` | `get_tooltip` |
| `/_agent/source_frame` | `get_source_frame` (takes `source_id`, no `client_id`) |
| `/_agent/screenshot` | `screenshot` (`max_width`, `quality`) |
| `/_agent/click`, `hover`, `set_field`, `toggle_dropdown`, `read_dropdown_options`, `add_node`, `position_node`, `connect_nodes`, `open_node`, `delete_node`, `delete_edge`, `highlight`, `clear_highlight` | tool of the same name |

Example: the runbook's
`POST /_agent/highlight {"client_id", "kind":"button", "target":"Save", "text":"Save"}`
becomes the MCP call `highlight(client_id=..., kind="button", target="Save", text="Save")`;
`GET /_agent/state?client_id=...` becomes `get_state(client_id=...)`.

Where the runbook and a tool's schema disagree, the tool's schema wins -- an
MCP client validates arguments strictly (`additionalProperties: false`) and
rejects unknown keys. In particular, **`click` takes only `client_id` and
`text`**: never send `kind` to it (use `highlight` with `kind` beforehand).

## 4. MCP tools available

- **Session**: `list_sessions`, `get_state`, `get_graph`, `get_notifications`
- **Inspect**: `get_text`, `get_tooltip`
- **Act**: `click`, `hover`, `set_field`, `toggle_dropdown`,
  `read_dropdown_options`, `add_node`, `position_node`, `connect_nodes`,
  `open_node`, `delete_node`, `delete_edge`
- **Narrate**: `highlight`, `clear_highlight`
- **Look**: `screenshot`, `get_source_frame` -- the only tools returning
  pixels (a JPEG) instead of structured state
- **Docs**: `get_documentation`

See [`mcp-endpoints.md`](../../../../../gui/mcp-endpoints.md) for full
signatures and edge cases (multi-select "Devices" fields, dropdown
disambiguation via `scope_id`, the canvas-vs-subflow scoping rule). If a tool
is missing, check `.mcp.json` in this directory.

## 5. Operating rules

- **Get the `client_id` first.** Call `list_sessions`; use the entry with
  `has_socket_connection: true`. If several are live, ask the user which.
- **Highlight, clear, act.** For every discrete GUI action: `highlight` the
  target, `clear_highlight`, then perform the action -- one action fully
  completed and verified before starting the next. Never batch a field change
  with the save that depends on it.
- **Verify before reporting.** Use `get_state`, `get_graph`, `get_text` or
  `get_notifications`; these are the authoritative checks and are preferred
  over screenshots. Wherever the runbook's Verification says screenshot, also
  call `screenshot` (`max_width=1280`, `quality=0.5`) and read the image --
  after each dialog opens, closes, or changes a multi-select. Use screenshots
  in addition to the read-only calls, never instead.
- **Notifications.** Before any action that produces one, record the current
  max `id` via `get_notifications`, then read with `since_id=<that id>` after
  the action.
- **Close every dropdown you open.** After `set_field` on a multi-select,
  `toggle_dropdown` the same label to close it, confirm `is_open: false`, and
  screenshot.
- **Never invent** a call shape or field label. If the runbook and
  `mcp-endpoints.md` don't cover it, inspect `get_state`/`get_graph` to find
  the real one.
- Standalone `sleep` of 30–60 s is blocked in Bash; use waits of 5–20 s and
  poll.

## 6. Known pitfalls (these override the runbook where they differ)

**General**
- `Force Stop All` and `Clear canvas` end a run; rebuild and relaunch before
  benchmarking again. Node ids change after a clear -- use the ids from the
  latest `add_node` results.
- After a clear, the palette's **Sources** group is collapsed, so highlighting
  palette `"Input"` returns `not_found`. Expand Sources first (highlight +
  click `"Sources"`); Sinks may need the same.
- Bare `"refresh"` is ambiguous (device-health recheck vs meta-key detect vs
  plot refresh). Use the full label: `"Re-check device health"` or
  `"plot refresh"`.

**Device health check**
- The result is a notification: `Unhealthy device(s): ...` (negative) or
  `All selected devices passed the health check` (positive). The button is
  `disabled: true` while it runs (minutes on first run; poll `get_state`).
- The check covers **only the devices selected when you click**, not the whole
  host. The `⚠ FAILED HEALTH CHECK` dropdown suffix exists only on the
  vLLM/VLM node, never on Vision -- trust the notification. (The runbook's
  Vision §11b/§11c say otherwise; they are wrong.)
- A failed device stays failed on re-check. Change the device instead.

**Changing a multi-select device** (never leave the field empty):
`toggle_dropdown` to open → `read_dropdown_options` → `set_field` the new
device (adds) → `set_field` the old one (removes) → `get_state` shows only the
new one → `toggle_dropdown` to close (`is_open: false`) → `screenshot`.
`set_field` toggles: it adds an unselected option and removes a selected one.
After Save the dropdown is off-screen; `open_node` to re-check it. On the
first open, the toggle can report `opened` with `is_open: false` and
`read_dropdown_options` can return `not_open` -- toggle again and read
immediately before concluding the list is empty; don't reopen the dialog.
Option format: `metis-0:23:0 (device 1)`.

**Compile and launch**
- A click on a disabled Compile button returns `ok` but does nothing; wait for
  `disabled: false`.
- Vision success: `Compiled 1 pipeline spec(s) ...` then `Launched 1
  pipeline(s)`. VLM has no YAML step: one `Launched 1 vLLM VLM server(s):
  <node_id> (port ...)`.
- **OpenCL failure** (`OpenCL not functional: Failed to get platform count!` +
  `SIGABRT`, not tied to a device): `set_field` `"OpenCL"` to `"false"`,
  confirm `checked: false`, regenerate the YAML (preview reads
  `--disable-opencl`), save it, wait for `Wrote ...`, compile again with a
  fresh baseline id. A failure naming `Device N` is fixed by changing the
  device instead.

**VLM node**
- The Artifact dropdown may hold a single, already-selected option;
  `set_field` returns `option_not_found` -- confirm via `get_state` and move on.
- `Image resize width/height (px)` appear only after `Is VLM (image input)` is
  on; read `get_state` before setting them.

**Benchmarking**
- If `drawer.open` is `false` after `hover` `enter` on `"benchmark settings
  edge"`, repeat once; after `leave`, `get_state` may briefly still say
  `open: true` -- read again.
- Sources appear in `get_state` `sources` a few seconds after `Open`.
- VLM chat: the drawer's Inference endpoint fields describe the last Vision
  pipeline -- skip that check; the chat panel's `(V/L)LM server` value
  (`<node_id> (1 instance, port(s) ...)`) is the real one. With a single
  server the dropdown holds it by default; read `get_state` rather than
  `read_dropdown_options`.
- Read replies with `get_text` `contains` a phrase unique to that reply (bare
  `"TTFT"` and the `"<node_id> ·"` header are ambiguous after a second
  reply -- match that reply's own value, e.g. `"TTFT 1.67s"`). The running
  average is `contains "avg (last"`.
- Each `Add image(s)` attaches one file and closes itself; check `get_text`
  `contains "images attached"` after each.
- VLM teardown: Force Stop All reports `Stopped 1 vLLM/LLM server(s):
  <node_id>`; after Clear canvas `get_graph` is `{"nodes":[],"edges":[]}`.
