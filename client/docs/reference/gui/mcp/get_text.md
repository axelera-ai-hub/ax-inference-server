# get_text

## Summary

Reads the text of the one visible element whose own text contains a substring.

## Detailed Description

### Behavior

- Searches the topmost modal dialog, or the whole page when none is open.
- The match is a case-insensitive substring of a visible leaf element.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_text(client_id: str, contains: str) -> dict
```

Route: `GET /_agent/get_text`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `contains` | `str` | - | Yes | Substring of the target element's own text. |

## Returns

`{"ok": true, "text": str}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several elements match equally well. | Use a longer or more exact text. The result returns `matched_count` and no `candidates`. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "get_text",
  "arguments": {
    "client_id": "<client_id>",
    "contains": "Compile"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -G http://127.0.0.1:8080/_agent/get_text --data-urlencode client_id=<client_id> --data-urlencode contains=Compile
```

## Edge Cases

- Two matching elements give `ambiguous` with `matched_count`. Use a longer substring.

## Related APIs

| API | Relationship |
|---|---|
| [get_tooltip](get_tooltip.md) | Reads tooltip text instead. |
| [get_notifications](get_notifications.md) | Reads toast text. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_text` (lines 177-191)
- `client/ui/gui/agent_surface.py::_agent_get_text` (lines 880-924)
