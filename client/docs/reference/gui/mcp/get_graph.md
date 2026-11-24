# get_graph

## Summary

Reads the canvas graph of one browser tab.

## Detailed Description

### Behavior

- Returns the `agent_nodes` and `agent_edges` of the tab's `PipelineFlow`.
- While an ROI node's subflow dialog is open, the result is that subflow's fixed skeleton graph.
- When the tab has no canvas, the result is the shared current graph.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_graph(client_id: str) -> dict
```

Route: `GET /_agent/graph`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |

## Returns

`dict` `{"nodes": [...], "edges": [...]}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "get_graph",
  "arguments": {
    "client_id": "<client_id>"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s "http://127.0.0.1:8080/_agent/graph?client_id=<client_id>"
```

## Edge Cases

- The route is a synchronous handler and runs no JavaScript.

## Related APIs

| API | Relationship |
|---|---|
| [add_node](add_node.md) | Adds a node. |
| [connect_nodes](connect_nodes.md) | Adds an edge. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_graph` (lines 162-174)
- `client/ui/gui/agent_surface.py::_agent_get_graph` (lines 1043-1055)
