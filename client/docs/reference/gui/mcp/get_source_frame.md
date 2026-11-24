# get_source_frame

## Summary

Fetches the newest saved frame of a Benchmarking source as a JPEG.

## Detailed Description

### Behavior

- Looks `source_id` up in `BENCHMARK_SOURCES`, lists the frame directory with the configured ring-buffer helper and reads the newest file.
- The tool takes no `client_id`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async get_source_frame(source_id: str) -> Image | dict
```

Route: `GET /_agent/source_frame`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `source_id` | `str` | - | Yes | Benchmarking source id. `get_state` lists ids under `sources`. |

## Returns

MCP tool: an `Image` or the error dict. Route: `{"ok": true, "image_base64": str, "format": "jpeg", "bytes": int}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |
| `not_found` | No Benchmarking source has that id. | Read ids from `get_state` under `sources`. |
| `no_frames_yet` | The source has no saved frame, or the frame file vanished. | Wait for the source to produce frames. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "get_source_frame",
  "arguments": {
    "source_id": "<source_id>"
  }
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s "http://127.0.0.1:8080/_agent/source_frame?source_id=<source_id>"
```

## Edge Cases

- An unknown source gives `ok: false`, not HTTP 404.

## Related APIs

| API | Relationship |
|---|---|
| [get_state](get_state.md) | Lists source ids. |
| [screenshot](screenshot.md) | Captures the whole tab. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_source_frame` (lines 461-474)
- `client/ui/gui/agent_surface.py::_agent_source_frame_route` (lines 1797-1800)
