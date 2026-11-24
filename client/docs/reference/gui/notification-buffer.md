# Notification buffer

## Overview

The GUI records every toast raised through `ui.notify` in a per-tab buffer. The tool `get_notifications` and the route `GET /_agent/notifications` read it. Agents poll the buffer to learn the outcome of asynchronous actions such as compile or launch.

## Attributes

| Name | Type | Description |
|---|---|---|
| `AGENT_NOTIFICATION_BUFFERS` | `dict[str, deque]` | Maps `client_id` to a `deque` of records. Stored on `core.app.state.agent_notification_buffers`. |
| `AGENT_NOTIFICATION_BUFFER_SIZE` | `int` | `200`. The `maxlen` of each deque. |
| `agent_notification_seq` | `int` | Counter on `core.app.state`. One counter serves all tabs. |

## Record

| Key | Type | Description |
|---|---|---|
| `id` | `int` | Value of the shared counter after increment. Starts at 1. |
| `ts` | `float` | `time.time()` when the toast fired. |
| `message` | `str` | `str(message)` of the `ui.notify` call. |
| `type` | `str | None` | The `type` keyword, or `None`. |
| `position` | `str` | The `position` keyword. Defaults to `bottom`. |

## Behavior

1. Importing `agent_surface` replaces `ui.notify` with a wrapper once. A second import keeps the original function.
2. The wrapper reads `ui.context.client.id`. Outside a client context it records nothing.
3. The wrapper appends a record to the deque of that client and calls the original `ui.notify` with the same arguments.
4. The read route returns the records with `id` greater than `since_id`, oldest first.

## Constraints

- Each tab keeps at most 200 records. The deque drops the oldest record first.
- The read route returns 404 for a `client_id` that is not connected. The code never removes a buffer, so the buffer of a closed tab stays in memory.
- A reload creates a new `client_id` and a new empty buffer.
- Ids rise across all tabs, so the ids within one tab are not consecutive.
- Concurrency behavior depends on the underlying runtime.

## Usage Examples

```bash
curl -s "http://127.0.0.1:8080/_agent/notifications?client_id=<client_id>&since_id=0"
```

```json
{"notifications": [{"id": 17, "ts": 1760000000.0, "message": "Compile finished", "type": "positive", "position": "bottom"}]}
```

The message text in the example is illustrative.

## Related

| Page | Relationship |
|---|---|
| [get_notifications](mcp/get_notifications.md) | The MCP tool. |
| [agent_surface](agent_surface.md) | Defines the buffer and wrapper. |

## Source Reference

- `client/ui/gui/agent_surface.py::AGENT_NOTIFICATION_BUFFERS` (lines 50-50)
- `client/ui/gui/agent_surface.py::AGENT_NOTIFICATION_BUFFER_SIZE` (lines 52-52)
