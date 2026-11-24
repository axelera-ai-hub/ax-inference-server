# delete_node

## Summary

Deletes a canvas node.

## Detailed Description

### Behavior

- Deletes the node and waits up to 3 s for it to disappear.
- The app refuses locked nodes.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async delete_node(client_id: str, node_id: str) -> dict
```

Route: `POST /_agent/delete_node`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

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
| `node_locked` | The node is locked. | Leave the node in place. |
| `node_still_present` | The node remained after 3 s. | Read the graph and retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "delete_node",
  "arguments": {
    "client_id": "<client_id>",
    "node_id": "net-1"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/delete_node -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "node_id": "net-1"}'
```

## Edge Cases

- Edge removal for the deleted node follows the canvas behavior. Behavior inferred from code inspection.

## Related APIs

| API | Relationship |
|---|---|
| [delete_edge](delete_edge.md) | Removes only an edge. |
| [add_node](add_node.md) | Creates nodes. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::delete_node` (lines 405-418)
- `client/ui/gui/agent_surface.py::_agent_delete_node_route` (lines 1872-1876)
