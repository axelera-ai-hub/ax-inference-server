# list_sessions

## Summary

Lists the connected browser tabs and their `client_id` values.

## Detailed Description

### Behavior

- Iterates NiceGUI `Client.instances` and reports one entry per client.
- Call this tool first. Every tool except `get_documentation` and `get_source_frame` needs a `client_id` from this list. See [Sessions and client_id](../sessions-and-client-id.md).

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The MCP server must reach the GUI app at `GUI_APP_BASE_URL` (default `http://127.0.0.1:8080`, the app's `GUI_APP_PORT`).
- The tool sends `X-Agent-Key` when `GUI_AGENT_API_KEY` is set in the MCP server environment.
- A non-2xx response raises `httpx.HTTPStatusError` in the tool. See [Error codes](../error-codes.md).

## Signature

```python
async list_sessions() -> dict
```

Route: `GET /_agent/sessions`. Header `X-Agent-Key` is required only when `GUI_AGENT_API_KEY` is set.

## Parameters

None.

## Returns

`dict` `{"sessions": [{"client_id": str, "has_socket_connection": bool | None}, ...]}`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| HTTP 401 | `GUI_AGENT_API_KEY` is set on the app and the `X-Agent-Key` header differs. | Set `GUI_AGENT_API_KEY` to the app value in the MCP server environment. |

Failure codes marked `ok: false` return with HTTP 200. See [Error codes](../error-codes.md).

## Usage Examples

### MCP call

```json
{
  "name": "list_sessions",
  "arguments": {}
}
```

### curl

The equivalent request against the GUI app. Add `-H "X-Agent-Key: $GUI_AGENT_API_KEY"` when the key is set.

```bash
curl -s http://127.0.0.1:8080/_agent/sessions
```

## Edge Cases

- The list is empty when no browser tab is open.
- `has_socket_connection` is `None` when the client has no such attribute.
- The route does not check `client_id`, so it never returns 404.

## Related APIs

| API | Relationship |
|---|---|
| [get_state](get_state.md) | Next call for a chosen tab. |
| [Sessions and client_id](../sessions-and-client-id.md) | Explains the id. |
| [Routes overview](../agent-routes.md) | Lists all `/_agent/*` routes. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::list_sessions` (lines 137-146)
- `client/ui/gui/agent_surface.py::_agent_list_sessions_route` (lines 1744-1752)
