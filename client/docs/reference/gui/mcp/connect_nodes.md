# connect_nodes

## Summary

Connects two canvas nodes with an edge.

## Detailed Description

### Behavior

- Adds the edge and waits up to 3 s for it to appear.
- The app refuses the call on an ROI subflow canvas, whose wiring is fixed.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async connect_nodes(client_id: str, source_id: str, target_id: str) -> dict
```

Route: `POST /_agent/connect_nodes`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `source_id` | `str` | - | Yes | Id of the source node. |
| `target_id` | `str` | - | Yes | Id of the target node. |

## Returns

`{"ok": true, "source": str, "target": str}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `canvas_not_found` | The tab has no canvas. | Open the Pipeline Editor tab. |
| `subflow_locked` | An ROI subflow dialog is open. | Close the subflow dialog. |
| `node_not_found` | A node id is missing. The result adds `missing`. | Read ids with [get_graph](get_graph.md). |
| `edge_never_appeared` | The edge did not appear within 3 s. | Check the connection rules, then retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "connect_nodes",
  "arguments": {
    "client_id": "<client_id>",
    "source_id": "input-1",
    "target_id": "net-1"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/connect_nodes -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "source_id": "input-1", "target_id": "net-1"}'
```

## Edge Cases

- An edge the editor rejects surfaces as `edge_never_appeared`. Behavior inferred from code inspection.

## Related APIs

| API | Relationship |
|---|---|
| [delete_edge](delete_edge.md) | Removes an edge. |
| [get_graph](get_graph.md) | Reads edges. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::connect_nodes` (lines 371-388)
- `client/ui/gui/agent_surface.py::_agent_connect_nodes_route` (lines 1858-1862)
