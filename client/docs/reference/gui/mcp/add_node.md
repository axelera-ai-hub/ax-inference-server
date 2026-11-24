# add_node

## Summary

Adds a node to the canvas by clicking its leaf in the node palette.

## Detailed Description

### Behavior

- Looks the label up in `AGENT_NODE_LABEL_MAP`. Unknown labels fail with `known_labels`.
- Expands the leaf's category when the leaf is not visible.
- Waits up to 5 s for the node `<catalog key>-<counter + 1>` to appear in the graph.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async add_node(client_id: str, label: str) -> dict
```

Route: `POST /_agent/add_node`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `label` | `str` | - | Yes | Exact visible palette label, for example `Input`, `Vision`, `Sink`, `(V/L)LM`. |

## Returns

`{"ok": true, "node_id": str, "position": ...}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `unknown_label` | The label is not a palette leaf. The result adds `known_labels`. | Use one of `known_labels`. |
| `category_not_found` | The leaf's category row was not found. The result adds `category`. | Take a `screenshot` and check the palette. |
| `leaf_not_found_after_expand` | The leaf is missing after the category expanded. The result adds `label`. | Retry after closing open dialogs. |
| `node_never_appeared` | The node did not appear within 5 s. The result adds `expected_id`. | Read the graph with [get_graph](get_graph.md) and retry. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "add_node",
  "arguments": {
    "client_id": "<client_id>",
    "label": "Input"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/add_node -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "label": "Input"}'
```

## Edge Cases

- Each call adds one node. The returned `node_id` is the expected id based on the shared node counter.

## Related APIs

| API | Relationship |
|---|---|
| [position_node](position_node.md) | Moves the new node. |
| [connect_nodes](connect_nodes.md) | Wires it. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::add_node` (lines 330-344)
- `client/ui/gui/agent_surface.py::_agent_add_node_route` (lines 1844-1848)
