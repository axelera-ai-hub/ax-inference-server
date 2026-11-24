#!/usr/bin/env python3
"""FastMCP server that exposes the Pipeline Editor GUI's /_agent/* HTTP routes as MCP tools.

Run it over stdio (default) or HTTP: `--transport {stdio,http} --host HOST --port PORT`. It is a pure HTTP client of the GUI app (app.py).

Note:
    GUI_APP_BASE_URL sets the app's base URL (default http://127.0.0.1:8080). GUI_AGENT_API_KEY, when set, is sent as the X-Agent-Key header on every call and must match the app's value. Every tool taking a client_id acts on the one browser tab with that id; get ids from list_sessions().
"""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from pydantic import Field

GUI_APP_BASE_URL = os.environ.get('GUI_APP_BASE_URL', 'http://127.0.0.1:8080')
GUI_AGENT_API_KEY = os.environ.get('GUI_AGENT_API_KEY', '')

_headers = {'X-Agent-Key': GUI_AGENT_API_KEY} if GUI_AGENT_API_KEY else {}
_http = httpx.AsyncClient(base_url=GUI_APP_BASE_URL, headers=_headers, timeout=30.0)

_GUI_DIR = Path(__file__).resolve().parent
CLIENT_DOCS_README = _GUI_DIR.parents[1] / 'docs' / 'README.md'
SERVER_DOCS_README = _GUI_DIR.parents[2] / 'server' / 'docs' / 'README.md'


def _read_docs_readme(path: Path) -> str:
    """Return the text of a docs README, or a '(failed to read ...)' message if it cannot be read."""
    try:
        return path.read_text()
    except OSError as exc:
        return f'(failed to read {path}: {exc})'

mcp = FastMCP(
    name='pipeline-editor-agent',
    instructions=(
        "Before driving anything, read the 'client-docs'/'server-docs' resources "
        "(or call get_documentation if your client can't fetch resources mid-task) "
        "for how the client library, compiler, and this GUI fit together -- re-read "
        "them any time, including mid-task, rather than relying on a stale memory "
        "of their contents. "
        "Drives the No-Code Pipeline Editor GUI's Pipeline Editor canvas, its node "
        "dialogs, and the Benchmarking tab -- the same /_agent/* primitives "
        "tests/*_e2e_agent_api.py uses. Call list_sessions first to find the "
        "client_id of the browser tab you want to drive (one per connected tab), "
        "then pass that client_id to every other tool. The canvas graph "
        "(get_graph/add_node/position_node/connect_nodes/delete_node/delete_edge) "
        "is scoped per client_id: normally the tab's outer canvas, but if that "
        "tab currently has an ROI node's subflow dialog open, these tools "
        "instead see and act on that subflow's own fixed skeleton graph -- "
        "whose wiring is locked (connect_nodes/delete_edge refuse on it) "
        "though its nodes' fields remain editable via open_node. "
        "highlight/clear_highlight draw a visual callout over a live element "
        "(button, field, dialog, canvas node, or a generic text/pointer "
        "fallback) -- useful before taking a screenshot, or to narrate a "
        "step-by-step walkthrough."
    ),
)


@mcp.resource(
    'docs://client',
    name='client-docs',
    description="Index of this repo's client-side docs (client library + this GUI) -- start here, then follow its own links.",
    mime_type='text/markdown',
)
def client_docs_resource() -> str:
    """Return the client-side docs index (client/docs/README.md) as the 'docs://client' resource."""
    return _read_docs_readme(CLIENT_DOCS_README)


@mcp.resource(
    'docs://server',
    name='server-docs',
    description="Index of this repo's server-side docs (inference server, vLLM/LLM serving, interfaces) -- start here, then follow its own links.",
    mime_type='text/markdown',
)
def server_docs_resource() -> str:
    """Return the server-side docs index (server/docs/README.md) as the 'docs://server' resource."""
    return _read_docs_readme(SERVER_DOCS_README)


@mcp.tool
def get_documentation(
    which: Annotated[Literal['client', 'server', 'all'], Field(
        description="'client' for the client library/GUI docs index, 'server' for the inference-server docs index, 'all' for both")] = 'all',
) -> dict:
    """Retrieve the repo's documentation indexes.

    Use this when the MCP client cannot fetch the 'client-docs'/'server-docs' resources mid-task.

    Args:
        which (str, optional): 'client', 'server' or 'all'. Defaults to 'all'.

    Returns:
        dict: Keys 'client' and/or 'server', each {'path': README path, 'content': README text}. An unreadable README yields a '(failed to read ...)' string as its content.
    """
    out: dict = {}
    if which in ('client', 'all'):
        out['client'] = {'path': str(CLIENT_DOCS_README), 'content': _read_docs_readme(CLIENT_DOCS_README)}
    if which in ('server', 'all'):
        out['server'] = {'path': str(SERVER_DOCS_README), 'content': _read_docs_readme(SERVER_DOCS_README)}
    return out


async def _get(path: str, **params: Any) -> dict:
    """Send a GET to the GUI app and return the decoded JSON body.

    Parameters whose value is None are omitted from the query string.

    Raises:
        httpx.HTTPStatusError: If the app answers with a non-2xx status (e.g. 401 bad key, 404 unknown client_id).
    """
    r = await _http.get(path, params={k: v for k, v in params.items() if v is not None})
    r.raise_for_status()
    return r.json()


async def _post(path: str, body: dict) -> dict:
    """Send a JSON POST to the GUI app and return the decoded JSON body.

    Raises:
        httpx.HTTPStatusError: If the app answers with a non-2xx status (e.g. 401 bad key, 404 unknown client_id).
    """
    r = await _http.post(path, json=body)
    r.raise_for_status()
    return r.json()


@mcp.tool
async def list_sessions() -> dict:
    """List the connected browser tabs of the GUI app.

    Call this first; pass a returned client_id to every other tool.

    Returns:
        dict: {'sessions': [{'client_id': str, 'has_socket_connection': bool | None}, ...]}.
    """
    return await _get('/_agent/sessions')


@mcp.tool
async def get_state(client_id: str) -> dict:
    """Read the visible UI state of one browser tab.

    Args:
        client_id (str): Tab id from list_sessions().

    Returns:
        dict: dialog_open, the Advanced Settings drawer state, and the visible buttons, toggles, fields and tabs, plus 'sources' (latest benchmark metrics per source_id). On failure {'ok': False, 'error': ...}.
    """
    return await _get('/_agent/state', client_id=client_id)


@mcp.tool
async def get_graph(client_id: str) -> dict:
    """Read the canvas graph of one browser tab.

    Reports the tab's outer canvas, or the subflow skeleton graph while an ROI node's subflow dialog is open.

    Args:
        client_id (str): Tab id from list_sessions().

    Returns:
        dict: {'nodes': [...], 'edges': [...]}.
    """
    return await _get('/_agent/graph', client_id=client_id)


@mcp.tool
async def get_text(
    client_id: str,
    contains: Annotated[str, Field(description="Substring of the target element's own rendered text")],
) -> dict:
    """Read the rendered text of the one visible element whose own text contains a substring.

    Args:
        client_id (str): Tab id from list_sessions().
        contains (str): Case-insensitive substring of the target element's own text.

    Returns:
        dict: {'ok': True, 'text': ...}, or {'ok': False, 'error': 'not_found' | 'ambiguous', ...}.
    """
    return await _get('/_agent/get_text', client_id=client_id, contains=contains)


@mcp.tool
async def get_notifications(client_id: str, since_id: int = 0) -> dict:
    """Read the toast notifications raised in a tab (ui.notify calls).

    Args:
        client_id (str): Tab id from list_sessions().
        since_id (int, optional): Return only notifications with an id greater than this. Defaults to 0.

    Returns:
        dict: {'notifications': [{'id', 'ts', 'message', 'type', 'position'}, ...]}.
    """
    return await _get('/_agent/notifications', client_id=client_id, since_id=since_id)


@mcp.tool
async def get_tooltip(client_id: str, label: str) -> dict:
    """Read the tooltip shown when hovering a labeled element.

    Args:
        client_id (str): Tab id from list_sessions().
        label (str): Substring of the element's text.

    Returns:
        dict: {'ok': True, 'text': ...}, or {'ok': False, ...} when the element is not found, is ambiguous, or shows no tooltip.
    """
    return await _post('/_agent/tooltip', {'client_id': client_id, 'label': label})


@mcp.tool
async def hover(
    client_id: str,
    text: Annotated[str, Field(description="Visible text, icon ligature name, aria-label, or alt -- matched the same way click() finds things")],
    action: Annotated[Literal['enter', 'leave'], Field(description="'enter' to start hovering, 'leave' to stop")] = 'enter',
) -> dict:
    """Start or stop hovering an element by dispatching synthetic mouse events.

    Args:
        client_id (str): Tab id from list_sessions().
        text (str): Visible text, icon ligature name, aria-label, or alt of the target.
        action (str, optional): 'enter' or 'leave'. Defaults to 'enter'.

    Returns:
        dict: {'ok': True, 'text': ...}, or {'ok': False, 'error': 'not_found' | 'ambiguous', ...}.
    """
    return await _post('/_agent/hover', {'client_id': client_id, 'text': text, 'action': action})


@mcp.tool
async def click(
    client_id: str,
    text: Annotated[str, Field(description="Visible text, icon ligature name (e.g. 'delete', 'play_arrow'), alt, or aria-label")],
) -> dict:
    """Click a button, tab, toggle, radio, labeled image or palette tree row by its visible text.

    When a modal dialog is open the match is looked up inside it first, then outside any dialog.

    Args:
        client_id (str): Tab id from list_sessions().
        text (str): Visible text, icon ligature name (e.g. 'delete', 'play_arrow'), alt, or aria-label.

    Returns:
        dict: {'ok': True, 'kind': ..., 'text': ...}, or {'ok': False, 'error': 'not_found' | 'ambiguous', ...}.
    """
    return await _post('/_agent/click', {'client_id': client_id, 'text': text})


@mcp.tool
async def set_field(
    client_id: str,
    label: str,
    value: Annotated[str, Field(description="'true'/'false' for a toggle or checkbox, otherwise the text/number/option value")],
    scope_id: Annotated[Optional[str], Field(description="Restrict the match to the element carrying this data-agent-id (e.g. a Benchmarking source's source_id) -- required whenever several widgets can render the identical label text, since label text alone then can't disambiguate them")] = None,
) -> dict:
    """Set a toggle, checkbox, text/number field or dropdown selection by label.

    Args:
        client_id (str): Tab id from list_sessions().
        label (str): Label text of the target widget.
        value (str): 'true'/'false' for a toggle or checkbox, otherwise the text, number or option value.
        scope_id (str, optional): data-agent-id of an element to restrict the match to. Needed when several widgets render the same label.

    Returns:
        dict: {'ok': True, 'kind': ...}, or {'ok': False, 'error': ...} (e.g. not_found, ambiguous, disabled, option_not_found).
    """
    body = {'client_id': client_id, 'label': label, 'value': value}
    if scope_id is not None:
        body['scope_id'] = scope_id
    return await _post('/_agent/set_field', body)


@mcp.tool
async def toggle_dropdown(
    client_id: str,
    label: str,
    scope_id: Annotated[Optional[str], Field(description="Restrict the match to the element carrying this data-agent-id, same as set_field's scope_id")] = None,
) -> dict:
    """Open a dropdown if it is closed, or close it if it is open.

    Args:
        client_id (str): Tab id from list_sessions().
        label (str): Label text of the dropdown field.
        scope_id (str, optional): data-agent-id of an element to restrict the match to.

    Returns:
        dict: {'ok': True, 'action': 'opened' | 'closed', 'is_open': bool}, or {'ok': False, 'error': ...}.
    """
    body = {'client_id': client_id, 'label': label}
    if scope_id is not None:
        body['scope_id'] = scope_id
    return await _post('/_agent/toggle_dropdown', body)


@mcp.tool
async def read_dropdown_options(
    client_id: str,
    label: str,
    scope_id: Annotated[Optional[str], Field(description="Restrict the match to the element carrying this data-agent-id, same as set_field's scope_id")] = None,
) -> dict:
    """Read every option of a dropdown that is already open.

    Open it first with toggle_dropdown.

    Args:
        client_id (str): Tab id from list_sessions().
        label (str): Label text of the dropdown field.
        scope_id (str, optional): data-agent-id of an element to restrict the match to.

    Returns:
        dict: {'ok': True, 'options': [{'text': str, 'selected': bool}, ...]}, or {'ok': False, 'error': ...} (e.g. not_open).
    """
    body = {'client_id': client_id, 'label': label}
    if scope_id is not None:
        body['scope_id'] = scope_id
    return await _post('/_agent/read_dropdown_options', body)


@mcp.tool
async def add_node(
    client_id: str,
    label: Annotated[str, Field(description="Exact visible palette label, e.g. 'Input', 'Vision', 'Sink', '(V/L)LM'")],
) -> dict:
    """Add a node to the canvas by clicking its leaf in the node palette.

    Args:
        client_id (str): Tab id from list_sessions().
        label (str): Exact visible palette label, e.g. 'Input', 'Vision', 'Sink', '(V/L)LM'.

    Returns:
        dict: {'ok': True, 'node_id': ..., 'position': ...}, or {'ok': False, 'error': ...} (unknown_label lists the known labels).
    """
    return await _post('/_agent/add_node', {'client_id': client_id, 'label': label})


@mcp.tool
async def position_node(
    client_id: str,
    node_id: str,
    frac_x: Annotated[float, Field(ge=0.0, le=1.0, description="Fraction of the canvas pane's current width")],
    frac_y: Annotated[float, Field(ge=0.0, le=1.0, description="Fraction of the canvas pane's current height")],
) -> dict:
    """Drag a canvas node to a position given as fractions of the canvas pane.

    Args:
        client_id (str): Tab id from list_sessions().
        node_id (str): Id of the node (see get_graph()).
        frac_x (float): Fraction of the pane's current width, 0.0 to 1.0.
        frac_y (float): Fraction of the pane's current height, 0.0 to 1.0.

    Returns:
        dict: {'ok': True, 'node_id': ..., 'position': ...}, or {'ok': False, 'error': ...}.
    """
    return await _post(
        '/_agent/position_node',
        {'client_id': client_id, 'node_id': node_id, 'frac_x': frac_x, 'frac_y': frac_y},
    )


@mcp.tool
async def connect_nodes(client_id: str, source_id: str, target_id: str) -> dict:
    """Connect two canvas nodes with an edge.

    Refused on an ROI subflow graph, whose wiring is locked.

    Args:
        client_id (str): Tab id from list_sessions().
        source_id (str): Id of the source node.
        target_id (str): Id of the target node.

    Returns:
        dict: {'ok': True, 'source': ..., 'target': ...}, or {'ok': False, 'error': ...}.
    """
    return await _post(
        '/_agent/connect_nodes',
        {'client_id': client_id, 'source_id': source_id, 'target_id': target_id},
    )


@mcp.tool
async def open_node(client_id: str, node_id: str) -> dict:
    """Open a canvas node's dialog by double-clicking it.

    Args:
        client_id (str): Tab id from list_sessions().
        node_id (str): Id of the node (see get_graph()).

    Returns:
        dict: {'ok': True, 'node_id': ...}, or {'ok': False, 'error': ...}.
    """
    return await _post('/_agent/open_node', {'client_id': client_id, 'node_id': node_id})


@mcp.tool
async def delete_node(client_id: str, node_id: str) -> dict:
    """Delete a canvas node.

    Locked nodes are refused.

    Args:
        client_id (str): Tab id from list_sessions().
        node_id (str): Id of the node (see get_graph()).

    Returns:
        dict: {'ok': True, 'node_id': ...}, or {'ok': False, 'error': ...}.
    """
    return await _post('/_agent/delete_node', {'client_id': client_id, 'node_id': node_id})


@mcp.tool
async def delete_edge(client_id: str, source_id: str, target_id: str) -> dict:
    """Delete the edge between two canvas nodes.

    Args:
        client_id (str): Tab id from list_sessions().
        source_id (str): Id of the edge's source node.
        target_id (str): Id of the edge's target node.

    Returns:
        dict: {'ok': True, 'source': ..., 'target': ...}, or {'ok': False, 'error': ...}.
    """
    return await _post(
        '/_agent/delete_edge',
        {'client_id': client_id, 'source_id': source_id, 'target_id': target_id},
    )


@mcp.tool
async def screenshot(client_id: str, max_width: int = 1280, quality: float = 0.5) -> Image | dict:
    """Capture a JPEG screenshot of a browser tab.

    Args:
        client_id (str): Tab id from list_sessions().
        max_width (int, optional): Downscale the image to at most this width in pixels. Defaults to 1280.
        quality (float, optional): JPEG quality, 0.0 to 1.0. Defaults to 0.5.

    Returns:
        Image | dict: The JPEG image, or the app's {'ok': False, 'error': ...} result when capture fails.
    """

    result = await _get(
        '/_agent/screenshot',
        client_id=client_id, max_width=max_width, quality=quality,
    )
    if not result.get('ok'):
        return result
    return Image(data=base64.b64decode(result['image_base64']), format='jpeg')


@mcp.tool
async def get_source_frame(source_id: str) -> Image | dict:
    """Fetch the latest saved frame of a Benchmarking source as a JPEG.

    Args:
        source_id (str): Benchmarking source id.

    Returns:
        Image | dict: The JPEG image, or {'ok': False, 'error': 'not_found' | 'no_frames_yet'}.
    """
    result = await _get('/_agent/source_frame', source_id=source_id)
    if not result.get('ok'):
        return result
    return Image(data=base64.b64decode(result['image_base64']), format='jpeg')


@mcp.tool
async def highlight(
    client_id: str,
    kind: Annotated[str, Field(description=(
        "'button'/'tab'/'toggle' (target: visible text/icon ligature/aria-label, "
        "same matching as click()), 'field' (target: the field's label, same "
        "matching as set_field()), 'node' (target: a canvas node id), 'edge' "
        "(the connection between two canvas nodes -- a Vue Flow edge, rendered "
        "as its own curve, not part of either node's box; identified by "
        "`source_id`/`target_id`, not `target`, same as connect_nodes()/"
        "delete_edge()), 'dialog' (no target needed -- the topmost open "
        "dialog's panel), 'text' (target: a substring of a plain element's own "
        "text, same matching as get_text()), 'palette' (target: a node-palette "
        "leaf's exact visible label, e.g. 'Input' -- same exact-match lookup as "
        "add_node(); use this instead of 'text'/'auto' when the leaf's label "
        "collides with its category's icon or an existing canvas node of the "
        "same name, e.g. 'Input' under the 'Sources' category), 'auto' (tries "
        "button/tab/toggle, then field, then text), or 'pointer' (no fitted box "
        "-- an arrow+label at a text-matched target or explicit x/y; the "
        "fallback for anything none of the other kinds fit)"
    ))] = 'auto',
    target: Annotated[Optional[str], Field(description="What to highlight -- see `kind`'s per-kind meaning; omit for kind='dialog' or kind='edge'")] = None,
    text: Annotated[Optional[str], Field(description="Optional callout text rendered next to the highlight, e.g. 'Double-click here'")] = None,
    id: Annotated[Optional[str], Field(description="Unique id so multiple highlights can coexist and be cleared independently; auto-generated if omitted")] = None,
    color: Annotated[Optional[str], Field(description="CSS color override, default a red-orange")] = None,
    x: Annotated[Optional[float], Field(ge=0.0, le=1.0, description="Viewport x fraction, kind='pointer' only, used when `target` can't be text-matched")] = None,
    y: Annotated[Optional[float], Field(ge=0.0, le=1.0, description="Viewport y fraction, kind='pointer' only")] = None,
    source_id: Annotated[Optional[str], Field(description="kind='edge' only -- the edge's source node id (see get_graph())")] = None,
    target_id: Annotated[Optional[str], Field(description="kind='edge' only -- the edge's target node id (see get_graph())")] = None,
) -> dict:
    """Draw a visual callout over a live element, useful before a screenshot or to narrate a walkthrough.

    How `target` is interpreted depends on `kind`; see the description of `kind`.

    Args:
        client_id (str): Tab id from list_sessions().
        kind (str, optional): What kind of element to highlight. Defaults to 'auto'.
        target (str, optional): What to highlight. Omit for kind='dialog' or kind='edge'.
        text (str, optional): Callout text rendered next to the highlight.
        id (str, optional): Unique id so several highlights can coexist; auto-generated if omitted.
        color (str, optional): CSS color override.
        x (float, optional): Viewport x fraction, kind='pointer' only.
        y (float, optional): Viewport y fraction, kind='pointer' only.
        source_id (str, optional): Edge source node id, kind='edge' only.
        target_id (str, optional): Edge target node id, kind='edge' only.

    Returns:
        dict: The result of the page's highlight call, or {'ok': False, 'error': ...}.
    """
    return await _post('/_agent/highlight', {
        'client_id': client_id, 'kind': kind, 'target': target, 'text': text,
        'id': id, 'color': color, 'x': x, 'y': y,
        'source_id': source_id, 'target_id': target_id,
    })


@mcp.tool
async def clear_highlight(client_id: str, id: Optional[str] = None) -> dict:
    """Remove one highlight, or all highlights in a tab.

    Args:
        client_id (str): Tab id from list_sessions().
        id (str, optional): Id of the highlight to remove. Removes all when omitted.

    Returns:
        dict: {'ok': True}.
    """
    return await _post('/_agent/clear_highlight', {'client_id': client_id, 'id': id})


def main() -> None:
    """Parse the command line and run the MCP server over stdio or HTTP."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=['stdio', 'http'], default='stdio',
                         help="stdio for Claude Code/Desktop; http for a network-reachable server (e.g. ADK's MCPToolset)")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8091)
    args = parser.parse_args()

    if args.transport == 'stdio':
        mcp.run()
    else:
        mcp.run(transport='http', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
