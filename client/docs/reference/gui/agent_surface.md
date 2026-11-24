# agent_surface

## Overview

`client/ui/gui/agent_surface.py` is the agent control surface of the GUI. It registers the `/_agent/*` routes on the NiceGUI app and holds the browser-side helpers behind them. Helpers run JavaScript in the target tab through `run_javascript` or call `PipelineFlow` methods. They return `{"ok": true, ...}` or `{"ok": false, "error": <code>, ...}`. The module is imported by `app.py`, which then calls `configure`.

## Public API

| Symbol | Kind | Description |
|---|---|---|
| `configure(*, read_file_bytes, benchmark_ring_buffer_names)` | function | Supplies the benchmark helpers owned by `benchmark.py`. Call it once at startup. |
| `BENCHMARK_SOURCES` | `dict` | Benchmark sources by `source_id`. Shared through `core.app.state.benchmark_sources`. |
| `current_graph` | `dict` | Shared graph, used when a tab has no canvas. Shared through `core.app.state.current_graph`. |
| `AGENT_NOTIFICATION_BUFFERS` | `dict` | Per-tab notification deques. See [Notification buffer](notification-buffer.md). |
| `AGENT_NOTIFICATION_BUFFER_SIZE` | `int` | `200` records per tab. |
| `AGENT_NODE_LABEL_MAP` | `dict` | Palette leaf label to `(NODE_CATALOG key, category label)`. Built from `PALETTE_TREE` and `NODE_CATALOG`. |
| `GUI_AGENT_API_KEY` | `str` | Shared secret from the environment. Empty disables the check. |

### configure

| Parameter | Type | Description |
|---|---|---|
| `read_file_bytes` | callable | Returns the bytes of a file path. Used by `/_agent/source_frame`. |
| `benchmark_ring_buffer_names` | callable | Returns the sorted frame file names of a frame directory. |

`/_agent/source_frame` needs both callables, so `app.py` must call `configure` before any frame request.

## Behavior

- The module wraps `ui.notify` once to record toasts. See [Notification buffer](notification-buffer.md).
- With a modal dialog open, lookups are scoped to that dialog.
- Routes are listed in the [routes overview](agent-routes.md). Failures are listed in [Error codes](error-codes.md).
- Concurrency behavior depends on the underlying runtime.

## Routes

The module registers 21 routes with FastAPI `Depends(_require_agent_key)`. Each route resolves `client_id` through `Client.instances` and calls one helper. The tool pages document the helper behavior.

## Related

| Page | Relationship |
|---|---|
| [agent_mcp_server](agent_mcp_server.md) | MCP client of these routes. |
| [Sessions and client_id](sessions-and-client-id.md) | Tab addressing. |

## Source Reference

- `client/ui/gui/agent_surface.py::configure` (lines 34-43)
- `client/ui/gui/agent_surface.py::AGENT_NODE_LABEL_MAP` (lines 1073-1073)
- `client/ui/gui/agent_surface.py::AGENT_NOTIFICATION_BUFFERS` (lines 50-50)
