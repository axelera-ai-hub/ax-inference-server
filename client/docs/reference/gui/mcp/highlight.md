# highlight

## Summary

Draws a visual callout over a live element.

## Detailed Description

### Behavior

- Calls `window.__annotateHighlight` in the tab. Only arguments that are not `None` are sent.
- For `kind="edge"` the app looks up the edge between `source_id` and `target_id` and uses its id as the target.
- The meaning of `target` depends on `kind`. See the kinds table.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async highlight(client_id: str, kind: str = 'auto', target=None, text=None, id=None, color=None, x=None, y=None, source_id=None, target_id=None) -> dict
```

Route: `POST /_agent/highlight`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `kind` | `str` | `'auto'` | No | Highlight kind. See the kinds table. |
| `target` | `str` or `None` | `None` | No | What to highlight. Omit for `dialog` and `edge`. |
| `text` | `str` or `None` | `None` | No | Callout text beside the highlight. |
| `id` | `str` or `None` | `None` | No | Id to clear this highlight later. Generated when omitted. |
| `color` | `str` or `None` | `None` | No | CSS color override. |
| `x` | `float` or `None` | `None` | No | Viewport x fraction, 0.0 to 1.0. Kind `pointer` only. |
| `y` | `float` or `None` | `None` | No | Viewport y fraction, 0.0 to 1.0. Kind `pointer` only. |
| `source_id` | `str` or `None` | `None` | No | Edge source node id. Kind `edge` only. |
| `target_id` | `str` or `None` | `None` | No | Edge target node id. Kind `edge` only. |

## Returns

The overlay result dict, or `{"ok": false, "error": ...}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `missing_source_or_target` | Kind `edge` without `source_id` or `target_id`. | Pass both ids. |
| `canvas_not_found` | Kind `edge` and the tab has no canvas. | Open the Pipeline Editor tab. |
| `edge_not_found` | No edge links the two nodes. | Read edges with [get_graph](get_graph.md). |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "highlight",
  "arguments": {
    "client_id": "<client_id>",
    "kind": "button",
    "target": "play_arrow",
    "text": "Click to run",
    "id": "run-hint"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s -X POST http://127.0.0.1:8080/_agent/highlight -H 'Content-Type: application/json' -d '{"client_id": "<client_id>", "kind": "button", "target": "play_arrow", "text": "Click to run", "id": "run-hint"}'
```

## Kinds

| Kind | Target | Matching |
|---|---|---|
| `button`, `tab`, `toggle` | Visible text, icon ligature or `aria-label`. | Same as `click`. |
| `field` | Field label. | Same as `set_field`. |
| `node` | Canvas node id. | Exact id. |
| `edge` | None. Use `source_id` and `target_id`. | Same as `connect_nodes`. |
| `dialog` | None. | Topmost open dialog panel. |
| `text` | Substring of a plain element's text. | Same as `get_text`. |
| `palette` | Exact palette leaf label. | Same lookup as `add_node`. |
| `auto` | Text or label. | Tries button, tab, toggle, then field, then text. |
| `pointer` | Text, or explicit `x` and `y`. | Draws an arrow with a label and no fitted box. |

## Edge Cases

- Highlights with different `id` values coexist.
- Use [clear_highlight](clear_highlight.md) to remove them.

## Related APIs

| API | Relationship |
|---|---|
| [clear_highlight](clear_highlight.md) | Removes highlights. |
| [screenshot](screenshot.md) | Captures the callout. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::highlight` (lines 477-530)
- `client/ui/gui/agent_surface.py::_agent_highlight_route` (lines 1886-1894)
