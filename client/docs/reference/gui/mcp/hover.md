# hover

## Summary

Starts or stops hovering an element with synthetic mouse events.

## Detailed Description

### Behavior

- Matches text like `click`, over a wider element set (anything with an `aria-label`), without dialog scoping.
- `enter` starts the hover. `leave` ends it.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async hover(client_id: str, text: str, action: Literal['enter','leave'] = 'enter') -> dict
```

Route: `POST /_agent/hover`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `text` | `str` | - | Yes | Visible text, icon ligature, `aria-label` or `alt` of the target. |
| `action` | `'enter'` or `'leave'` | `'enter'` | No | Event to dispatch. |

## Returns

`{"ok": true, "text": str}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several elements match equally well. | Use a longer or more exact text. The result lists `candidates` where available. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "hover",
  "arguments": {
    "client_id": "<client_id>",
    "text": "Compile",
    "action": "enter"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/hover -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "text": "Compile", "action": "enter"}'
```

## Edge Cases

- The MCP tool restricts `action` to `enter` and `leave`. The route model accepts any string.

## Related APIs

| API | Relationship |
|---|---|
| [get_tooltip](get_tooltip.md) | Hovers and reads in one call. |
| [click](click.md) | Same matching, clicks. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::hover` (lines 222-238)
- `client/ui/gui/agent_surface.py::_agent_hover_route` (lines 1790-1794)
