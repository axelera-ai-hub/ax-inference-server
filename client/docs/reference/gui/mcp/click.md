# click

## Summary

Clicks a button, tab, toggle, radio, labeled image or palette row by its visible text.

## Detailed Description

### Behavior

- Matches visible text, icon ligature name, `alt` or `aria-label`. An exact case-insensitive match beats a substring match.
- With a modal dialog open, the dialog is searched first, then the page outside any dialog.
- Clicking a palette category row clicks its expand arrow.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async click(client_id: str, text: str) -> dict
```

Route: `POST /_agent/click`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `text` | `str` | - | Yes | Visible text, icon ligature (for example `delete`, `play_arrow`), `alt` or `aria-label`. |

## Returns

`{"ok": true, "kind": str, "text": str}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `not_found` | No visible element matches. | Check the text with `get_state`, or narrow it. |
| `ambiguous` | Several matches tie. The result adds `matched_count` and `candidates`. | Use a longer or more exact text. The result lists `candidates` where available. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "click",
  "arguments": {
    "client_id": "<client_id>",
    "text": "play_arrow"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/click -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "text": "play_arrow"}'
```

## Edge Cases

- A Benchmarking source thumbnail is clickable by its source name through `alt` or `aria-label`.

## Related APIs

| API | Relationship |
|---|---|
| [set_field](set_field.md) | Edits fields. |
| [get_state](get_state.md) | Lists clickable targets. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::click` (lines 241-257)
- `client/ui/gui/agent_surface.py::_agent_click_route` (lines 1755-1759)
