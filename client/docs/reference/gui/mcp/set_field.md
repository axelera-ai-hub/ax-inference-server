# set_field

## Summary

Sets a toggle, checkbox, text or number field, or dropdown selection by label.

## Detailed Description

### Behavior

- A toggle or checkbox is clicked only when its state differs. The values `true`, `1`, `on` and `yes` mean on.
- A writable input receives the value with `input`, `change` and `blur` events.
- A select is opened and the option is picked by exact text, or by unique substring. The menu scrolls while options remain undiscovered. An already open menu is reused.
- Without `scope_id`, the search covers the topmost dialog, or the page.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async set_field(client_id: str, label: str, value: str, scope_id: Optional[str] = None) -> dict
```

Route: `POST /_agent/set_field`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `label` | `str` | - | Yes | Label text of the widget (substring match for fields). |
| `value` | `str` | - | Yes | `true`/`false` for toggles and checkboxes, otherwise the text, number or option. |
| `scope_id` | `str` or `None` | `None` | No | `data-agent-id` of an element that restricts the match. Needed when several widgets share a label. |

## Returns

`{"ok": true, "kind": "toggle" | "input" | "select", ...}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several elements match equally well. | Use a longer or more exact text. Select-option ambiguity also returns `candidates`. Other matches return `matched_count` only. |
| `disabled` | The matched widget is disabled. | Enable the widget first, for example by setting the field that unlocks it. |
| `scope_not_found` | No element carries the given `scope_id`. | Omit `scope_id` to search the whole page, or pass the `data-agent-id` of an element that exists in the tab. |
| `option_not_found` | No select option matches `value`. The result adds `rendered_options_seen`. | Read the options with [read_dropdown_options](read_dropdown_options.md). |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "set_field",
  "arguments": {
    "client_id": "<client_id>",
    "label": "Name",
    "value": "demo"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/set_field -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "label": "Name", "value": "demo", "scope_id": null}'
```

## Edge Cases

- The body omits `scope_id` in the MCP tool when it is `None`.
- Use `scope_id` when several Benchmarking sources render the same label.

## Related APIs

| API | Relationship |
|---|---|
| [toggle_dropdown](toggle_dropdown.md) | Opens or closes a select. |
| [read_dropdown_options](read_dropdown_options.md) | Lists select options. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::set_field` (lines 260-281)
- `client/ui/gui/agent_surface.py::_agent_set_field_route` (lines 1762-1766)
