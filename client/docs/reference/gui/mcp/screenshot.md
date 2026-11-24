# screenshot

## Summary

Captures a JPEG screenshot of a browser tab.

## Detailed Description

### Behavior

- Renders the page with html2canvas, which must be loaded in the page.
- html2canvas cannot re-fetch images with `blob:` URLs, such as the pinned stream's live frame.
- In the cloned document, the tool replaces each such image with a canvas that holds the current pixels.
- The image is downscaled to `max_width` when wider.
- The MCP tool decodes `image_base64` and returns a FastMCP `Image` (JPEG). The route returns base64 JSON.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async screenshot(client_id: str, max_width: int = 1280, quality: float = 0.5) -> Image | dict
```

Route: `GET /_agent/screenshot`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `client_id` | `str` | - | Yes | Tab id from `list_sessions`. |
| `max_width` | `int` | `1280` | No | Maximum output width in pixels. |
| `quality` | `float` | `0.5` | No | JPEG quality, 0.0 to 1.0. |

## Returns

MCP tool: an `Image` or the error dict. Route: `{"ok": true, "image_base64": str, "format": "jpeg", "width": int, "height": int, "bytes": int}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| HTTP 404 | No connected client has that `client_id`. | Call `list_sessions` and use a returned id. |
| `html2canvas_not_loaded` | html2canvas is not available in the page. | Check that the page can load the html2canvas script from cdnjs, then retry. |
| `malformed_data_url` | The capture result is not a data URL. | Retry. |
| `js_exception` | The browser call raised. The `detail` key holds the message. | Check that the tab is still open, then retry. |
| `js_error` | The browser call returned a value that is not a dict. | Retry. Take a `screenshot` if it persists. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "screenshot",
  "arguments": {
    "client_id": "<client_id>",
    "max_width": 1280,
    "quality": 0.5
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s "http://127.0.0.1:8080/_agent/screenshot?client_id=<client_id>&max_width=1280&quality=0.5" | python3 -c 'import sys,json,base64; open("shot.jpg","wb").write(base64.b64decode(json.load(sys.stdin)["image_base64"]))'
```

## Edge Cases

- The tool does not clamp `quality` to 0.0 to 1.0. Behavior inferred from code inspection.

## Related APIs

| API | Relationship |
|---|---|
| [get_source_frame](get_source_frame.md) | Fetches a saved benchmark frame. |
| [highlight](highlight.md) | Annotate before capturing. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::screenshot` (lines 439-458)
- `client/ui/gui/agent_surface.py::_agent_screenshot_route` (lines 1803-1812)
