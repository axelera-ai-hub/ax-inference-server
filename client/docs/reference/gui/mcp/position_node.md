# position_node

## Summary

Drags a canvas node to a position given as fractions of the canvas pane.

## Detailed Description

### Behavior

- Animates the drag. The target is `frac_x` of the pane width and `frac_y` of the pane height.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async position_node(client_id: str, node_id: str, frac_x: float, frac_y: float) -> dict
```

Route: `POST /_agent/position_node`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `node_id` | `str` | - | Yes | Node id from `get_graph`. |
| `frac_x` | `float` | - | Yes | Fraction of the pane width, 0.0 to 1.0. |
| `frac_y` | `float` | - | Yes | Fraction of the pane height, 0.0 to 1.0. |

## Returns

`{"ok": true, "node_id": str, "position": ...}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `out_of_range` | `frac_x` or `frac_y` is outside [0.0, 1.0]. | Pass fractions in range. |
| `canvas_not_found` | The tab has no canvas. | Open the Pipeline Editor tab. |
| `node_not_found` | The graph has no such node. | Read ids with [get_graph](get_graph.md). |
| `node_not_rendered` | The node exists but is not rendered. | Retry after the canvas settles. |
| `node_disappeared` | The node vanished during the drag. | Read the graph and retry. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "position_node",
  "arguments": {
    "client_id": "<client_id>",
    "node_id": "input-1",
    "frac_x": 0.2,
    "frac_y": 0.5
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/position_node -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "node_id": "input-1", "frac_x": 0.2, "frac_y": 0.5}'
```

## Edge Cases

- The MCP tool schema enforces the 0.0 to 1.0 range. The route returns `out_of_range`.

## Related APIs

| API | Relationship |
|---|---|
| [get_graph](get_graph.md) | Lists node ids. |
| [add_node](add_node.md) | Creates nodes. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::position_node` (lines 347-368)
- `client/ui/gui/agent_surface.py::_agent_position_node_route` (lines 1851-1855)
