# get_tooltip

## Summary

Reads the tooltip shown when hovering a labeled element.

## Detailed Description

### Behavior

- Dispatches enter events, waits 0.4 s, reads the visible tooltip, then dispatches leave events.
- Interactive controls are tried before leaf text elements.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_tooltip(client_id: str, label: str) -> dict
```

Route: `POST /_agent/tooltip`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `label` | `str` | - | Yes | Substring of the element's text. |

## Returns

`{"ok": true, "text": str}`. When no non-empty tooltip appears, the result is `{"ok": false, "text": null}` with no `error` key.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element contains the label. | Use a different label substring. |
| `ambiguous` | Several elements match. The result adds `matched_count`. | Use a longer or more exact label. |
| `ok: false` with `text: null` | The element shows no non-empty tooltip. The result has no `error` key. | [hover](hover.md) the element and read with [get_text](get_text.md). |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "get_tooltip",
  "arguments": {
    "client_id": "<client_id>",
    "label": "Compile"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/tooltip -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "label": "Compile"}'
```

## Edge Cases

- A lookup that matches no element returns `not_found`. A lookup that matches several returns `ambiguous`.

## Related APIs

| API | Relationship |
|---|---|
| [hover](hover.md) | Hovers without reading. |
| [get_text](get_text.md) | Reads element text. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_tooltip` (lines 208-219)
- `client/ui/gui/agent_surface.py::_agent_tooltip_route` (lines 1823-1827)
