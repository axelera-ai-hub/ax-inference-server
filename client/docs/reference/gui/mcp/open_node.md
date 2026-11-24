# open_node

## Summary

Opens a canvas node's dialog by double-clicking it.

## Detailed Description

### Behavior

- Double-clicks the node and waits up to 5 s for a new modal dialog.
- Fields of the opened dialog are editable with `set_field`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async open_node(client_id: str, node_id: str) -> dict
```

Route: `POST /_agent/open_node`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `node_id` | `str` | - | Yes | Node id from `get_graph`. |

## Returns

`{"ok": true, "node_id": str}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `canvas_not_found` | The tab has no canvas. | Open the Pipeline Editor tab. |
| `node_not_found` | The graph has no such node. | Read ids with [get_graph](get_graph.md). |
| `node_not_rendered` | The node is not rendered. | Retry after the canvas settles. |
| `dialog_never_opened` | No new modal dialog appeared within 5 s. | Take a `screenshot` and retry. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "open_node",
  "arguments": {
    "client_id": "<client_id>",
    "node_id": "input-1"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/open_node -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "node_id": "input-1"}'
```

## Edge Cases

- Opening an ROI node's subflow dialog switches the graph tools to the subflow graph.

## Related APIs

| API | Relationship |
|---|---|
| [set_field](set_field.md) | Edits dialog fields. |
| [click](click.md) | Closes dialogs by button text. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::open_node` (lines 391-402)
- `client/ui/gui/agent_surface.py::_agent_open_node_route` (lines 1865-1869)
