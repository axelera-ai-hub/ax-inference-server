# Error codes

## Overview

The agent layer reports failures in two ways. The app returns HTTP errors for authorization and unknown tabs. Helpers return `{"ok": false, "error": <code>, ...}` with HTTP 200 for everything else.

## HTTP status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `GUI_AGENT_API_KEY` is set on the app and `X-Agent-Key` is missing or differs. Detail: `missing or invalid X-Agent-Key header`. | Send the correct key. |
| 404 | No connected client has the `client_id`. Detail: `no connected client with id '<id>'`. | Call `list_sessions`. |
| 422 | The request is missing a required field or has a wrong type (FastAPI validation). | Correct the request. |

The MCP tools raise `httpx.HTTPStatusError` for these codes. `list_sessions`, `get_source_frame` and `get_documentation` never return 404.

## Result error codes

| Code | Meaning | Tools |
|---|---|---|
| `not_found` | No visible element matches. For `get_source_frame`: unknown `source_id`. | `click`, `hover`, `get_text`, `get_tooltip`, `set_field`, `toggle_dropdown`, `read_dropdown_options`, `get_source_frame` |
| `ambiguous` | Several elements match equally well. | `click`, `hover`, `get_text`, `get_tooltip`, `set_field`, `toggle_dropdown`, `read_dropdown_options` |
| `disabled` | The matched widget is disabled. | `set_field`, `toggle_dropdown`, `read_dropdown_options` |
| `scope_not_found` | No element carries the `scope_id`. | `set_field`, `toggle_dropdown`, `read_dropdown_options` |
| `option_not_found` | No select option matches. Adds `rendered_options_seen`. | `set_field` |
| `not_a_dropdown` | The field is not a select. | `toggle_dropdown` |
| `qselect_ref_not_found` | The QSelect element was not found. | `toggle_dropdown` |
| `not_open` | The dropdown menu is closed. | `read_dropdown_options` |
| `unknown_label` | The label is not a palette leaf. Adds `known_labels`. | `add_node` |
| `category_not_found` | The palette category row was not found. | `add_node` |
| `leaf_not_found_after_expand` | The leaf is missing after expanding its category. | `add_node` |
| `node_never_appeared` | The node did not appear within 5 s. | `add_node` |
| `out_of_range` | `frac_x` or `frac_y` is outside [0.0, 1.0]. | `position_node` |
| `canvas_not_found` | The tab has no canvas. | `position_node`, `connect_nodes`, `delete_node`, `delete_edge`, `open_node`, `highlight` |
| `node_not_found` | The graph has no such node. | `position_node`, `connect_nodes`, `delete_node`, `open_node` |
| `node_not_rendered` | The node is not rendered. | `position_node`, `open_node` |
| `node_disappeared` | The node vanished during the drag. | `position_node` |
| `subflow_locked` | The ROI subflow wiring is fixed. | `connect_nodes` |
| `edge_never_appeared` | The edge did not appear within 3 s. | `connect_nodes` |
| `node_locked` | The node is locked. | `delete_node` |
| `node_still_present` | The node remained 3 s after deletion. | `delete_node` |
| `edge_not_found` | No edge links the nodes. | `delete_edge`, `highlight` |
| `edge_still_present` | The edge remained 3 s after deletion. | `delete_edge` |
| `dialog_never_opened` | No new modal dialog appeared within 5 s. | `open_node` |
| `missing_source_or_target` | Kind `edge` without both node ids. | `highlight` |
| `html2canvas_not_loaded` | html2canvas is not loaded in the page. | `screenshot` |
| `malformed_data_url` | The capture is not a data URL. | `screenshot` |
| `no_frames_yet` | The source has no saved frame. | `get_source_frame` |
| `js_exception` | The browser call raised. Adds `detail`. | All tools that run JavaScript. |
| `js_error` | The browser call returned a non-dict. | Same as `js_exception`, except `add_node`, `position_node`, `open_node` and `clear_highlight`. |

## Edge Cases

- A tool call that returns `ok: false` is a normal MCP result, not a tool error.
- Dialog scoping: a dialog counts as open only while the Quasar class `q-dialog--modal` is present. The class drops as soon as a close starts.

## Related

| Page | Relationship |
|---|---|
| [agent_surface](agent_surface.md) | Produces the codes. |
| [Routes overview](agent-routes.md) | Lists routes. |

## Source Reference

- `client/ui/gui/agent_surface.py::_require_agent_key` (lines 1610-1622)
- `client/ui/gui/agent_surface.py::_resolve_agent_client` (lines 1625-1640)
