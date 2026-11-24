# get_state

## Summary

Reads the visible UI state of one browser tab.

## Detailed Description

### Behavior

- Runs JavaScript in the tab and collects the visible dialog flag, drawer, buttons, toggles, fields and tabs.
- The app adds `sources`, which maps each Benchmarking `source_id` to its `latest_metrics` dict (empty when none).
- Each field entry holds `label`, `value`, `kind` (`select`, or the input type), `disabled` and `in_dialog`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_state(client_id: str) -> dict
```

Route: `GET /_agent/state`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |

## Returns

`dict` with `dialog_open` (bool), `drawer` (open flag and rect, or `None`), `buttons`, `toggles`, `fields`, `tabs` and `sources`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "get_state",
  "arguments": {
    "client_id": "<client_id>"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s "http://127.0.0.1:8080/_agent/state?client_id=<client_id>"
```

## Edge Cases

- Only visible elements are listed.
- `sources` covers all Benchmarking sources, not only those of the tab.

## Related APIs

| API | Relationship |
|---|---|
| [click](click.md) | Acts on listed buttons and tabs. |
| [set_field](set_field.md) | Edits listed fields. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_state` (lines 149-159)
- `client/ui/gui/agent_surface.py::_agent_get_state` (lines 748-877)
