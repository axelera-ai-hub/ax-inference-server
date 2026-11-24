# Agent routes overview

## Overview

`agent_surface.py` registers 21 HTTP routes under `/_agent/*` on the GUI app. The port is `GUI_APP_PORT` (default 8080). Each route maps to one MCP tool. The tool `get_documentation` has no route. Every tool page documents its route with a curl example.

## Authentication

Routes require the header `X-Agent-Key` only when `GUI_AGENT_API_KEY` is set in the app environment. Otherwise they are open. Treat the routes as local-control endpoints.

## Routes

| Method | Path | Tool | Selector |
|---|---|---|---|
| GET | `/_agent/sessions` | [list_sessions](mcp/list_sessions.md) | none |
| GET | `/_agent/state` | [get_state](mcp/get_state.md) | query `client_id` |
| GET | `/_agent/graph` | [get_graph](mcp/get_graph.md) | query `client_id` |
| GET | `/_agent/get_text` | [get_text](mcp/get_text.md) | query `client_id`, `contains` |
| GET | `/_agent/notifications` | [get_notifications](mcp/get_notifications.md) | query `client_id`, `since_id` |
| POST | `/_agent/tooltip` | [get_tooltip](mcp/get_tooltip.md) | body `client_id`, `label` |
| POST | `/_agent/hover` | [hover](mcp/hover.md) | body `client_id`, `text`, `action` |
| POST | `/_agent/click` | [click](mcp/click.md) | body `client_id`, `text` |
| POST | `/_agent/set_field` | [set_field](mcp/set_field.md) | body `client_id`, `label`, `value`, `scope_id` |
| POST | `/_agent/toggle_dropdown` | [toggle_dropdown](mcp/toggle_dropdown.md) | body `client_id`, `label`, `scope_id` |
| POST | `/_agent/read_dropdown_options` | [read_dropdown_options](mcp/read_dropdown_options.md) | body `client_id`, `label`, `scope_id` |
| POST | `/_agent/add_node` | [add_node](mcp/add_node.md) | body `client_id`, `label` |
| POST | `/_agent/position_node` | [position_node](mcp/position_node.md) | body `client_id`, `node_id`, `frac_x`, `frac_y` |
| POST | `/_agent/connect_nodes` | [connect_nodes](mcp/connect_nodes.md) | body `client_id`, `source_id`, `target_id` |
| POST | `/_agent/open_node` | [open_node](mcp/open_node.md) | body `client_id`, `node_id` |
| POST | `/_agent/delete_node` | [delete_node](mcp/delete_node.md) | body `client_id`, `node_id` |
| POST | `/_agent/delete_edge` | [delete_edge](mcp/delete_edge.md) | body `client_id`, `source_id`, `target_id` |
| GET | `/_agent/screenshot` | [screenshot](mcp/screenshot.md) | query `client_id`, `max_width`, `quality` |
| GET | `/_agent/source_frame` | [get_source_frame](mcp/get_source_frame.md) | query `source_id` |
| POST | `/_agent/highlight` | [highlight](mcp/highlight.md) | body `client_id`, `kind`, `target`, ... |
| POST | `/_agent/clear_highlight` | [clear_highlight](mcp/clear_highlight.md) | body `client_id`, `id` |

## Status codes

See [Error codes](error-codes.md). Routes return 401 and 404 as HTTP errors. FastAPI validation returns 422 for a missing or mistyped field. All other failures return HTTP 200 with `ok: false`.

## Usage Examples

```bash
curl -s http://127.0.0.1:8080/_agent/sessions
curl -s -X POST http://127.0.0.1:8080/_agent/click \
  -H 'Content-Type: application/json' -H "X-Agent-Key: $GUI_AGENT_API_KEY" \
  -d '{"client_id": "<client_id>", "text": "play_arrow"}'
```

## Related

| Page | Relationship |
|---|---|
| [agent_surface](agent_surface.md) | Module that registers the routes. |
| [agent_mcp_server](agent_mcp_server.md) | MCP wrapper over the routes. |

## Source Reference

- `client/ui/gui/agent_surface.py` (route functions `_agent_*_route`)
