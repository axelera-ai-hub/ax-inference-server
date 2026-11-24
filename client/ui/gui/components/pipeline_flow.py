"""NiceGUI wrapper around the Vue Flow node-graph canvas used by the pipeline editor.

Exposes `PipelineFlow`, a `ui.element` backed by `pipeline_flow.js` and the bundled Vue Flow library.
"""

from collections.abc import Callable

from nicegui import ui


class PipelineFlow(
    ui.element,
    component='pipeline_flow.js',
    esm={'vue_flow_bundle': 'dist'},
):

    """Editable node/edge canvas rendered in the browser by the Vue Flow component.

    Server-side methods forward to the JS component through `run_method`; graph edits made in the browser
    are reported back through the `graph_changed` event. The canvas keeps its own undo stack on the client.

    Attributes:
        agent_nodes (list[dict]): Server-side copy of the nodes, initialised from `nodes`. Read by the agent surface; callers overwrite it from `graph_changed` events.
        agent_edges (list[dict]): Server-side copy of the edges, initialised from `edges`. Same usage as `agent_nodes`.
        agent_scope (str): Which graph this canvas holds, 'outer' for the main pipeline or 'roi_subflow' for the ROI dialog subflow.
    """
    def __init__(
        self,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        *,
        on_graph_changed: Callable | None = None,
        on_debug_event: Callable | None = None,
        on_node_dblclick: Callable | None = None,
        show_clear_button: bool = True,
        agent_scope: str = 'outer',
    ) -> None:
        """Create the canvas and register event handlers.

        Args:
            nodes (list[dict] | None, optional): Initial Vue Flow nodes. Defaults to empty.
            edges (list[dict] | None, optional): Initial Vue Flow edges. Defaults to empty.
            on_graph_changed (Callable | None, optional): Handler for the `graph_changed` event (payload has `nodes` and `edges`).
            on_debug_event (Callable | None, optional): Handler for the `debug_event` event (recorded mouse/keyboard events).
            on_node_dblclick (Callable | None, optional): Handler for the `node_dblclick` event (payload has node `id` and `data`).
            show_clear_button (bool, optional): Show the "Clear canvas" control button. Defaults to True.
            agent_scope (str, optional): Value stored in `agent_scope`. Defaults to 'outer'.
        """
        super().__init__()
        self._props['nodes'] = nodes or []
        self._props['edges'] = edges or []
        self._props['showClearButton'] = show_clear_button
        self.agent_nodes: list[dict] = list(nodes or [])
        self.agent_edges: list[dict] = list(edges or [])
        self.agent_scope = agent_scope
        if on_graph_changed is not None:
            self.on('graph_changed', on_graph_changed)
        if on_debug_event is not None:
            self.on('debug_event', on_debug_event)
        if on_node_dblclick is not None:
            self.on('node_dblclick', on_node_dblclick)

    def add_node(self, node: dict) -> None:
        """Add a node to the canvas (records an undo snapshot)."""
        self.run_method('add_node', node)

    def move_node(self, node_id: str, screen_x: float, screen_y: float) -> None:
        """Move a node so it sits at the given screen (viewport) coordinates."""
        self.run_method('move_node', node_id, screen_x, screen_y)

    def connect_nodes(
        self,
        source: str,
        target: str,
        source_handle: str | None = None,
        target_handle: str | None = None,
    ) -> None:
        """Create an edge between two nodes, replacing links that use the same handles.

        Args:
            source (str): Id of the source node.
            target (str): Id of the target node.
            source_handle (str | None, optional): Source handle id.
            target_handle (str | None, optional): Target handle id.
        """
        self.run_method('connect_nodes', source, target, source_handle, target_handle)

    def set_graph(self, nodes: list[dict], edges: list[dict]) -> None:
        """Replace the whole graph with the given nodes and edges (records an undo snapshot)."""
        self.run_method('set_graph', nodes, edges)

    def delete_node(self, node_id: str) -> None:
        """Delete a node and its edges; locked nodes are refused with a toast."""
        self.run_method('delete_node', node_id)

    def delete_edge(self, edge_id: str) -> None:
        """Delete the edge with the given id."""
        self.run_method('delete_edge', edge_id)

    def set_recording(self, enabled: bool) -> None:
        """Start or stop emitting `debug_event` events for mouse and keyboard input."""
        self.run_method('set_recording', enabled)

    def update_node_data(self, node_id: str, data: dict) -> None:
        """Replace the `data` payload of a node."""
        self.run_method('update_node_data', node_id, data)
