# read_dropdown_options

## Summary

Reads every option of a dropdown whose menu is already open.

## Detailed Description

### Behavior

- Scrolls the menu to the top, then page by page (at most 40 pages), and collects option texts.
- Open the menu first with `toggle_dropdown`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async read_dropdown_options(client_id: str, label: str, scope_id: Optional[str] = None) -> dict
```

Route: `POST /_agent/read_dropdown_options`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `label` | `str` | - | Yes | Label text of the dropdown field. |
| `scope_id` | `str` or `None` | `None` | No | `data-agent-id` of an element that restricts the match. Needed when several widgets share a label. |

## Returns

`{"ok": true, "options": [{"text": str, "selected": bool}, ...]}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several elements match equally well. | Use a longer or more exact text. The result returns `matched_count` and no `candidates`. |
| `disabled` | The matched widget is disabled. | Enable the widget first, for example by setting the field that unlocks it. |
| `not_open` | The menu of the field is not open. | Call [toggle_dropdown](toggle_dropdown.md) first. |
| `scope_not_found` | No element carries the given `scope_id`. | Omit `scope_id` to search the whole page, or pass the `data-agent-id` of an element that exists in the tab. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "read_dropdown_options",
  "arguments": {
    "client_id": "<client_id>",
    "label": "Model"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/read_dropdown_options -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "label": "Model"}'
```

## Edge Cases

- The scan stops after 40 pages, so a very long list can be truncated. Behavior inferred from code inspection.

## Related APIs

| API | Relationship |
|---|---|
| [toggle_dropdown](toggle_dropdown.md) | Opens the menu. |
| [set_field](set_field.md) | Selects an option. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::read_dropdown_options` (lines 306-327)
- `client/ui/gui/agent_surface.py::_agent_read_dropdown_options_route` (lines 1776-1780)
