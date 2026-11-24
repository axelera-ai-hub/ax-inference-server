# get_notifications

## Summary

Reads the toast notifications raised in one tab, newer than a given id.

## Detailed Description

### Behavior

- Returns the records of the tab's notification buffer whose `id` exceeds `since_id`, oldest first.
- Every `ui.notify` call is recorded. See [Notification buffer](../notification-buffer.md).
- The `id` values come from one counter shared by all tabs. Poll with the highest `id` seen.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_notifications(client_id: str, since_id: int = 0) -> dict
```

Route: `GET /_agent/notifications`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `since_id` | `int` | `0` | No | Return only records with a greater `id`. |

## Returns

`{"notifications": [{"id": int, "ts": float, "message": str, "type": str or null, "position": str}, ...]}`. `ts` is `time.time()`. `position` defaults to `bottom`.

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
  "name": "get_notifications",
  "arguments": {
    "client_id": "<client_id>",
    "since_id": 0
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s "http://127.0.0.1:8080/_agent/notifications?client_id=<client_id>&since_id=0"
```

## Edge Cases

- A tab keeps at most 200 records. Older ones drop out.
- A reconnected tab has a new `client_id` and an empty buffer.
- The route does not execute JavaScript and does not wait for new records.

## Related APIs

| API | Relationship |
|---|---|
| [Notification buffer](../notification-buffer.md) | Buffer and wrapper details. |
| [get_state](get_state.md) | Reads other UI state. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_notifications` (lines 194-205)
- `client/ui/gui/agent_surface.py::_agent_get_notifications_route` (lines 1815-1820)
