# agent_mcp_server

## Overview

`client/ui/gui/agent_mcp_server.py` is a FastMCP server named `pipeline-editor-agent`. It exposes the GUI app's `/_agent/*` routes as 22 MCP tools and two documentation resources. The module is an HTTP client of the GUI app (`app.py`) and holds no GUI state. Agents use it to drive the Pipeline Editor canvas, node dialogs and the Benchmarking tab. See [MCP endpoints](../../gui/mcp-endpoints.md) for the concept page.

## Running

```bash
python client/ui/gui/agent_mcp_server.py                       # stdio (default)
python client/ui/gui/agent_mcp_server.py --transport http --host 127.0.0.1 --port 8091
```

| Option | Default | Description |
|---|---|---|
| `--transport` | `stdio` | `stdio` for Claude Code and Claude Desktop. `http` for a network-reachable server. |
| `--host` | `127.0.0.1` | Bind address for the `http` transport. |
| `--port` | `8091` | Port of the MCP server for the `http` transport. |

The port 8091 belongs to the MCP server. The GUI app listens on `GUI_APP_PORT` (default 8080), and the tools call that port.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GUI_APP_BASE_URL` | `http://127.0.0.1:8080` | Base URL of the GUI app. |
| `GUI_AGENT_API_KEY` | empty | When set, sent as header `X-Agent-Key` on every call. Must match the app value. |

The HTTP client uses a 30 s timeout.

## Public API

| Symbol | Kind | Description |
|---|---|---|
| `mcp` | `FastMCP` | The server instance. Name `pipeline-editor-agent`. |
| `main()` | function | Parses the command line and runs the server over stdio or HTTP. |
| `GUI_APP_BASE_URL` | `str` | Base URL read from the environment. |
| `GUI_AGENT_API_KEY` | `str` | Shared secret read from the environment. |
| `CLIENT_DOCS_README` | `Path` | `client/docs/README.md`. |
| `SERVER_DOCS_README` | `Path` | `server/docs/README.md`. |
| `client_docs_resource()` | resource | `docs://client`. See [MCP resources](mcp-resources.md). |
| `server_docs_resource()` | resource | `docs://server`. See [MCP resources](mcp-resources.md). |

## Tools

All 22 tools are listed in the [index](index.md). `get_documentation` reads local files. The other 21 tools each call one `/_agent/*` route. See the [routes overview](agent-routes.md).

## Server instructions

The server sends these instructions to the MCP client.

- Read the `client-docs` and `server-docs` resources, or call `get_documentation`, before driving anything.
- Call `list_sessions` first and pass the chosen `client_id` to every other tool.
- Graph tools are scoped per `client_id`. While an ROI node's subflow dialog is open, they act on the subflow skeleton graph. `connect_nodes` refuses to rewire that graph with `subflow_locked`.
- `highlight` and `clear_highlight` draw callouts for screenshots and walkthroughs.

## Error handling

The module raises `httpx.HTTPStatusError` when the app answers with a non-2xx status. Application failures return `{"ok": false, "error": ...}` with HTTP 200. See [Error codes](error-codes.md).

## Related

| Page | Relationship |
|---|---|
| [agent_surface](agent_surface.md) | Implements the routes this module calls. |
| [Routes overview](agent-routes.md) | Maps tools to routes. |
| [Sessions and client_id](sessions-and-client-id.md) | Explains the tab id. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::mcp` (lines 41-65)
- `client/ui/gui/agent_mcp_server.py::main` (lines 547-559)
