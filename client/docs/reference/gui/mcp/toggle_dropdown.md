# toggle_dropdown

## Summary

Opens a dropdown when it is closed and closes it when it is open.

## Detailed Description

### Behavior

- Closing calls `hidePopup()` on the QSelect, because synthetic events do not close a Quasar menu.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async toggle_dropdown(client_id: str, label: str, scope_id: Optional[str] = None) -> dict
```

Route: `POST /_agent/toggle_dropdown`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `label` | `str` | - | Yes | Label text of the dropdown field. |
| `scope_id` | `str` or `None` | `None` | No | `data-agent-id` of an element that restricts the match. Needed when several widgets share a label. |

## Returns

`{"ok": true, "action": "opened" | "closed", "is_open": bool}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several elements match equally well. | Use a longer or more exact text. The result returns `matched_count` and no `candidates`. |
| `disabled` | The matched widget is disabled. | Enable the widget first, for example by setting the field that unlocks it. |
| `not_a_dropdown` | The matched field is not a select. | Target a select field. |
| `scope_not_found` | No element carries the given `scope_id`. | Omit `scope_id` to search the whole page, or pass the `data-agent-id` of an element that exists in the tab. |
| `qselect_ref_not_found` | The QSelect element for the field was not found. | Retry. Take a `screenshot` to check the field state. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "toggle_dropdown",
  "arguments": {
    "client_id": "<client_id>",
    "label": "Model"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/toggle_dropdown -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "label": "Model"}'
```

## Edge Cases

- Call it twice to leave a menu closed after reading it.

## Related APIs

| API | Relationship |
|---|---|
| [read_dropdown_options](read_dropdown_options.md) | Reads the open menu. |
| [set_field](set_field.md) | Picks an option directly. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::toggle_dropdown` (lines 284-303)
- `client/ui/gui/agent_surface.py::_agent_toggle_dropdown_route` (lines 1769-1773)
