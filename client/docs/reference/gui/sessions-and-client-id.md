# Sessions and client_id

## Overview

Every browser tab that opens the GUI is one NiceGUI `Client` with a unique `client_id`. The agent layer addresses a tab by this id. The route `GET /_agent/sessions` and the tool `list_sessions` list the ids.

## Attributes

| Name | Type | Description |
|---|---|---|
| `client_id` | `str` | Key of the tab in NiceGUI `Client.instances`. |
| `has_socket_connection` | `bool | None` | Whether the tab's websocket is attached. `None` when the client lacks the attribute. |

## Behavior

- `GET /_agent/sessions` returns `{"sessions": [{"client_id": str, "has_socket_connection": bool | None}, ...]}`.
- Every other route except `/_agent/source_frame` takes a `client_id`. The app resolves it with `Client.instances`.
- An unknown id returns HTTP 404 with `no connected client with id '<id>'`.
- Canvas tools act on the tab's own canvas. While an ROI node's subflow dialog is open, they act on the subflow skeleton graph.
- A page reload creates a new `client_id`. Call `list_sessions` again.

## Usage Examples

```bash
curl -s http://127.0.0.1:8080/_agent/sessions
```

```json
{"sessions": [{"client_id": "9d5f...", "has_socket_connection": true}]}
```

## Related

| Page | Relationship |
|---|---|
| [list_sessions](mcp/list_sessions.md) | The MCP tool. |
| [Error codes](error-codes.md) | Documents the 404 response. |
| [Notification buffer](notification-buffer.md) | Buffers are keyed by `client_id`. |

## Source Reference

- `client/ui/gui/agent_surface.py::_agent_list_sessions_route` (lines 1744-1752)
- `client/ui/gui/agent_surface.py::_resolve_agent_client` (lines 1625-1640)
