# clear_highlight

## Summary

Removes one highlight, or all highlights in a tab.

## Detailed Description

### Behavior

- Removes the highlight with the given `id`. Removes all highlights when `id` is omitted.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async clear_highlight(client_id: str, id: Optional[str] = None) -> dict
```

Route: `POST /_agent/clear_highlight`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `id` | `str` or `None` | `None` | No | Id of the highlight to remove. |

## Returns

`{"ok": true}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "clear_highlight",
  "arguments": {
    "client_id": "<client_id>",
    "id": "run-hint"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/clear_highlight -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "id": "run-hint"}'
```

## Edge Cases

- An unknown `id` is not reported. Behavior inferred from code inspection.

## Related APIs

| API | Relationship |
|---|---|
| [highlight](highlight.md) | Creates highlights. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::clear_highlight` (lines 533-544)
- `client/ui/gui/agent_surface.py::_agent_clear_highlight_route` (lines 1897-1901)
