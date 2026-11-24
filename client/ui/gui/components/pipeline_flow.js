/**
 * NiceGUI custom element wrapping Vue Flow: an editable node/edge canvas with undo, copy/paste,
 * context-menu delete, a clear-canvas confirmation and optional input recording.
 *
 * Python-callable methods (see `pipeline_flow.py`): add_node, move_node, connect_nodes, set_graph,
 * delete_node, delete_edge, set_recording, update_node_data.
 * Events emitted: graph_changed, debug_event, node_dblclick.
 */
import { VueFlow, Background, Controls, ControlButton, useVueFlow } from "vue_flow_bundle";

// Maximum number of undo snapshots kept.
const UNDO_STACK_LIMIT = 20;
// Gives each canvas instance a unique Vue Flow store id.
let _canvasIdCounter = 0;

/** Default a node's handles to right (source) and left (target) unless the node overrides them. */
function withHandlePositions(node) {
  return { sourcePosition: "right", targetPosition: "left", ...node };
}

/** Apply `withHandlePositions` to every node; tolerates null. */
function normalizeNodes(nodes) {
  return (nodes || []).map(withHandlePositions);
}

export default {
  components: { VueFlow, Background, Controls, ControlButton },
  props: {
    nodes: { type: Array, default: () => [] },
    edges: { type: Array, default: () => [] },
    showClearButton: { type: Boolean, default: true },
  },
  emits: ["graph_changed", "debug_event", "node_dblclick"],
  data() {
    return {
      canvasId: `pipeline-canvas-${_canvasIdCounter++}`,
      localNodes: normalizeNodes(this.nodes),
      localEdges: this.edges,
      defaultEdgeOptions: { markerEnd: { type: "arrowclosed", width: 16, height: 16 } },
      contextMenu: { visible: false, x: 0, y: 0, nodeId: null },
      toast: { visible: false, message: "" },
      clearConfirmVisible: false,
    };
  },
  watch: {
    nodes(value) {
      this.localNodes = normalizeNodes(value);
    },
    edges(value) {
      this.localEdges = value;
    },
  },
  /**
   * Wire up Vue Flow events and the document-level listeners.
   *
   * Registers connect/change handlers, click-position tracking (used as the paste anchor), the optional
   * input recorder (mouse events throttled to one per 20 ms) and the Ctrl/Cmd+C, +V, +Z shortcuts, which are
   * ignored while a text field has focus. Pasted nodes and edges get ids suffixed `copy-N`.
   */
  mounted() {
    const { onConnect, onNodesChange, onEdgesChange, screenToFlowCoordinate } = useVueFlow(this.canvasId);
    this._screenToFlowCoordinate = screenToFlowCoordinate;
    this.$nextTick(() => {
      const fitViewBtn = this.$el.querySelector(".vue-flow__controls-fitview");
      if (fitViewBtn) {
        fitViewBtn.setAttribute("title", "Fit view");
        fitViewBtn.setAttribute("aria-label", "Fit View");
      }
    });
    onConnect((connection) => {
      this.handleConnection(connection);
    });
    onNodesChange(() => this.$nextTick(() => this.emit_graph()));
    onEdgesChange(() => this.$nextTick(() => this.emit_graph()));

    this._lastClickFlowPos = null;
    this.recordClickFlowPos = (event) => {
      this._lastClickFlowPos = screenToFlowCoordinate({ x: event.clientX, y: event.clientY });
    };

    this._recording = false;
    this._lastMoveEmitAt = 0;
    const emitDebugEvent = (partial) => {
      if (!this._recording) return;
      this.$emit("debug_event", { t: Math.round(performance.now() - this._recordStartTime), ...partial });
    };
    this._onRecordMouseDown = (event) => emitDebugEvent({ type: "mousedown", x: event.clientX, y: event.clientY, button: event.button });
    this._onRecordMouseUp = (event) => emitDebugEvent({ type: "mouseup", x: event.clientX, y: event.clientY, button: event.button });
    this._onRecordMouseMove = (event) => {
      if (!this._recording) return;
      const now = performance.now();
      if (now - this._lastMoveEmitAt < 20) return;
      this._lastMoveEmitAt = now;
      emitDebugEvent({ type: "mousemove", x: event.clientX, y: event.clientY });
    };
    this._onRecordWheel = (event) => emitDebugEvent({ type: "wheel", x: event.clientX, y: event.clientY, deltaX: event.deltaX, deltaY: event.deltaY, ctrlKey: event.ctrlKey });
    this._onRecordKeydown = (event) =>
      emitDebugEvent({ type: "keydown", key: event.key, ctrlKey: event.ctrlKey, metaKey: event.metaKey, shiftKey: event.shiftKey, altKey: event.altKey });
    this._onRecordKeyup = (event) =>
      emitDebugEvent({ type: "keyup", key: event.key, ctrlKey: event.ctrlKey, metaKey: event.metaKey, shiftKey: event.shiftKey, altKey: event.altKey });
    document.addEventListener("mousedown", this._onRecordMouseDown);
    document.addEventListener("mouseup", this._onRecordMouseUp);
    document.addEventListener("mousemove", this._onRecordMouseMove);
    document.addEventListener("wheel", this._onRecordWheel, { passive: true });
    document.addEventListener("keydown", this._onRecordKeydown);
    document.addEventListener("keyup", this._onRecordKeyup);

    this._onKeydown = (event) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) return;
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "c") {
        event.preventDefault();
        const selected = this.localNodes.filter((n) => n.selected);
        if (selected.length) {
          const selectedIds = new Set(selected.map((n) => n.id));
          const innerEdges = this.localEdges.filter((e) => selectedIds.has(e.source) && selectedIds.has(e.target));
          const anchor = {
            x: Math.min(...selected.map((n) => n.position.x)),
            y: Math.min(...selected.map((n) => n.position.y)),
          };
          this._clipboard = {
            nodes: selected.map((n) => ({ ...n, position: { ...n.position }, data: { ...(n.data || {}) } })),
            edges: innerEdges.map((e) => ({ ...e })),
            anchor,
          };
          this._lastClickFlowPos = null;
          const edgeNote = innerEdges.length ? ` and ${innerEdges.length} link${innerEdges.length > 1 ? "s" : ""}` : "";
          this.showToast(`Copied ${selected.length} node${selected.length > 1 ? "s" : ""}${edgeNote}`);
        } else {
          this.showToast("Nothing selected -- Ctrl/Cmd-click (or Shift-drag) to select node(s) first");
        }
      } else if (key === "v") {
        event.preventDefault();
        if (this._clipboard && this._clipboard.nodes.length) {
          this.pushUndoSnapshot();
          this._pasteCounter = (this._pasteCounter || 0) + 1;
          const suffix = `copy-${this._pasteCounter}`;
          const idMap = new Map();
          let dx = 60;
          let dy = 60;
          if (this._lastClickFlowPos) {
            dx = this._lastClickFlowPos.x - this._clipboard.anchor.x;
            dy = this._lastClickFlowPos.y - this._clipboard.anchor.y;
          }
          const pastedNodes = this._clipboard.nodes.map((n) => {
            const newId = `${n.id}-${suffix}`;
            idMap.set(n.id, newId);
            return {
              ...n,
              id: newId,
              position: { x: n.position.x + dx, y: n.position.y + dy },
              selected: false,
            };
          });
          const pastedEdges = this._clipboard.edges.map((e) => ({
            ...e,
            id: `${e.id}-${suffix}`,
            source: idMap.get(e.source),
            target: idMap.get(e.target),
          }));
          this.localNodes = [...this.localNodes, ...pastedNodes];
          this.localEdges = [...this.localEdges, ...pastedEdges];
          this.emit_graph();
          const edgeNote = pastedEdges.length ? ` and ${pastedEdges.length} link${pastedEdges.length > 1 ? "s" : ""}` : "";
          this.showToast(`Pasted ${pastedNodes.length} node${pastedNodes.length > 1 ? "s" : ""}${edgeNote}`);
        } else {
          this.showToast("Clipboard is empty -- copy node(s) first (Ctrl/Cmd+C)");
        }
      } else if (key === "z") {
        event.preventDefault();
        this.undo();
      }
    };
    document.addEventListener("keydown", this._onKeydown);
  },
  /** Remove document-level listeners and pending toast timer. */
  beforeUnmount() {
    document.removeEventListener("keydown", this._onKeydown);
    document.removeEventListener("mousedown", this._onRecordMouseDown);
    document.removeEventListener("mouseup", this._onRecordMouseUp);
    document.removeEventListener("mousemove", this._onRecordMouseMove);
    document.removeEventListener("wheel", this._onRecordWheel);
    document.removeEventListener("keydown", this._onRecordKeydown);
    document.removeEventListener("keyup", this._onRecordKeyup);
    if (this._toastTimeout) clearTimeout(this._toastTimeout);
  },
  methods: {
    /** Show a transient message at the bottom of the canvas for 1.8 s. */
    showToast(message) {
      if (this._toastTimeout) clearTimeout(this._toastTimeout);
      this.toast = { visible: true, message };
      this._toastTimeout = setTimeout(() => {
        this.toast.visible = false;
      }, 1800);
    },
    /** Save a copy of the current nodes and edges on the undo stack, dropping the oldest beyond the limit. */
    pushUndoSnapshot() {
      if (!this._undoStack) this._undoStack = [];
      this._undoStack.push({
        nodes: this.localNodes.map((n) => ({ ...n, position: { ...n.position }, data: { ...(n.data || {}) } })),
        edges: this.localEdges.map((e) => ({ ...e })),
      });
      if (this._undoStack.length > UNDO_STACK_LIMIT) this._undoStack.shift();
    },
    /** Restore the most recent undo snapshot and emit `graph_changed`; toast if the stack is empty. */
    undo() {
      if (this._undoStack && this._undoStack.length) {
        const snapshot = this._undoStack.pop();
        this.localNodes = snapshot.nodes;
        this.localEdges = snapshot.edges;
        this.emit_graph();
        this.showToast("Undid last change");
      } else {
        this.showToast("Nothing to undo");
      }
    },
    /** Emit `graph_changed` with the current nodes and edges. */
    emit_graph() {
      this.$emit("graph_changed", {
        nodes: this.localNodes,
        edges: this.localEdges,
      });
    },
    /**
     * Start or stop emitting `debug_event` input events.
     * Starting resets the time origin and emits a `meta` event with the window size.
     */
    set_recording(enabled) {
      this._recording = enabled;
      if (enabled) {
        this._recordStartTime = performance.now();
        this._lastMoveEmitAt = 0;
        this.$emit("debug_event", { type: "meta", t: 0, width: window.innerWidth, height: window.innerHeight });
      }
    },
    /** Append a node (with default handle positions) and emit `graph_changed`. */
    add_node(node) {
      this.pushUndoSnapshot();
      this.localNodes = [...this.localNodes, withHandlePositions(node)];
      this.emit_graph();
    },
    /** Move a node to the given screen coordinates, converted to flow coordinates. No-op for an unknown id. */
    move_node(id, screenX, screenY) {
      const index = this.localNodes.findIndex((n) => n.id === id);
      if (index === -1) return;
      const position = this._screenToFlowCoordinate({ x: screenX, y: screenY });
      const updated = [...this.localNodes];
      updated[index] = { ...updated[index], position };
      this.localNodes = updated;
      this.emit_graph();
    },
    /**
     * Add an edge for a new connection.
     * Each node side allows one link: edges already using the same source handle or target handle are
     * removed first, with an undo snapshot and a toast.
     */
    handleConnection(connection) {
      const displaced = this.localEdges.filter(
        (e) =>
          (e.source === connection.source && (e.sourceHandle ?? null) === (connection.sourceHandle ?? null)) ||
          (e.target === connection.target && (e.targetHandle ?? null) === (connection.targetHandle ?? null))
      );
      if (displaced.length) {
        this.pushUndoSnapshot();
        const displacedIds = new Set(displaced.map((e) => e.id));
        this.localEdges = this.localEdges.filter((e) => !displacedIds.has(e.id));
      }
      this._edgeCounter = (this._edgeCounter || 0) + 1;
      const newEdge = { ...connection, id: `${connection.source}->${connection.target}-${this._edgeCounter}` };
      this.localEdges = [...this.localEdges, newEdge];
      this.emit_graph();
      if (displaced.length) {
        this.showToast(`Replaced existing link${displaced.length > 1 ? "s" : ""} -- each node allows only one link per side`);
      }
    },
    /** Python entry point: connect two nodes through `handleConnection`; missing handles become null. */
    connect_nodes(source, target, sourceHandle, targetHandle) {
      this.handleConnection({
        source,
        target,
        sourceHandle: sourceHandle ?? null,
        targetHandle: targetHandle ?? null,
      });
    },
    /** Replace the whole graph (with undo snapshot) and emit `graph_changed`. */
    set_graph(nodes, edges) {
      this.pushUndoSnapshot();
      this.localNodes = normalizeNodes(nodes);
      this.localEdges = edges;
      this.emit_graph();
    },
    /** Show the clear-canvas confirmation overlay. */
    confirmClearGraph() {
      this.clearConfirmVisible = true;
    },
    /** Hide the clear-canvas confirmation overlay. */
    cancelClearGraph() {
      this.clearConfirmVisible = false;
    },
    /** Remove all nodes and edges (undoable) and close the confirmation overlay. */
    clearGraph() {
      this.pushUndoSnapshot();
      this.localNodes = [];
      this.localEdges = [];
      this.emit_graph();
      this.clearConfirmVisible = false;
      this.showToast("Canvas cleared");
    },
    /** Open the "Delete node" context menu at the cursor for the right-clicked node. */
    onNodeContextMenu({ event, node }) {
      event.preventDefault();
      this.contextMenu = { visible: true, x: event.clientX, y: event.clientY, nodeId: node.id };
    },
    /** Close the node context menu. */
    hideContextMenu() {
      this.contextMenu.visible = false;
    },
    /** Close the context menu and remember the click position as the next paste anchor. */
    onPaneClick(event) {
      this.hideContextMenu();
      this.recordClickFlowPos(event);
    },
    /** Close the context menu and remember the click position as the next paste anchor. */
    onNodeClick({ event }) {
      this.hideContextMenu();
      this.recordClickFlowPos(event);
    },
    /** Emit `node_dblclick` with a copy of the node's id and data. */
    onNodeDoubleClick({ event, node }) {
      event.preventDefault();
      this.$emit("node_dblclick", { id: node.id, data: { ...(node.data || {}) } });
    },
    /** Replace a node's `data` and emit `graph_changed`. No-op for an unknown id. */
    update_node_data(id, data) {
      const index = this.localNodes.findIndex((n) => n.id === id);
      if (index === -1) return;
      const updated = [...this.localNodes];
      updated[index] = { ...updated[index], data };
      this.localNodes = updated;
      this.emit_graph();
    },
    /** Delete a node and its edges (undoable). Nodes with `data.locked` are kept and a toast explains why. */
    delete_node(id) {
      const node = this.localNodes.find((n) => n.id === id);
      if (!node) return;
      if (node.data && node.data.locked) {
        this.showToast("This node is part of a fixed internal structure and can't be deleted");
        return;
      }
      this.pushUndoSnapshot();
      this.localNodes = this.localNodes.filter((n) => n.id !== id);
      this.localEdges = this.localEdges.filter((e) => e.source !== id && e.target !== id);
      this.emit_graph();
    },
    /** Delete the node the context menu was opened on, then close the menu. */
    deleteContextNode() {
      const id = this.contextMenu.nodeId;
      if (id) this.delete_node(id);
      this.hideContextMenu();
    },
    /** Delete an edge by id (undoable). No-op for an unknown id. */
    delete_edge(edgeId) {
      if (!this.localEdges.some((e) => e.id === edgeId)) return;
      this.pushUndoSnapshot();
      this.localEdges = this.localEdges.filter((e) => e.id !== edgeId);
      this.emit_graph();
    },
  },
  template: `
    <div style="height: 600px; width: 100%; border: 1px solid #ddd; border-radius: 4px; position: relative;">
      <VueFlow
        :id="canvasId"
        v-model:nodes="localNodes"
        v-model:edges="localEdges"
        :default-edge-options="defaultEdgeOptions"
        :fit-view-on-init="true"
        :delete-key-code="['Backspace', 'Delete']"
        :connection-radius="8"
        @node-context-menu="onNodeContextMenu"
        @pane-click="onPaneClick"
        @node-click="onNodeClick"
        @node-double-click="onNodeDoubleClick"
        @move-start="hideContextMenu"
      >
        <Background :gap="16" />
        <Controls>
          <ControlButton v-if="showClearButton" title="Clear canvas" aria-label="Clear Canvas" @click="confirmClearGraph">
            <i class="material-icons" style="font-size: 16px; line-height: 1;">delete</i>
          </ControlButton>
        </Controls>
      </VueFlow>
      <div
        v-if="clearConfirmVisible"
        style="position: absolute; inset: 0; background: rgba(0,0,0,0.35); z-index: 1001; display: flex; align-items: center; justify-content: center;"
        @click="cancelClearGraph"
      >
        <div
          style="background: white; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.25); padding: 20px 24px; min-width: 280px; font-size: 14px;"
          @click.stop
        >
          <div style="font-weight: 600; margin-bottom: 8px;">Clear canvas?</div>
          <div style="color: #555; margin-bottom: 16px;">This removes every node and edge. Ctrl+Z can undo it.</div>
          <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <button
              style="padding: 6px 14px; border: 1px solid #ccc; border-radius: 4px; background: white; cursor: pointer;"
              @click="cancelClearGraph"
            >No</button>
            <button
              style="padding: 6px 14px; border: none; border-radius: 4px; background: #d32f2f; color: white; cursor: pointer;"
              @click="clearGraph"
            >Yes</button>
          </div>
        </div>
      </div>
      <div
        v-if="contextMenu.visible"
        :style="'position: fixed; left: ' + contextMenu.x + 'px; top: ' + contextMenu.y + 'px; background: white; border: 1px solid #ccc; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); padding: 6px 14px; cursor: pointer; z-index: 1000; font-size: 14px;'"
        @click="deleteContextNode"
      >Delete node</div>
      <div
        v-if="toast.visible"
        style="position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%); background: rgba(33,33,33,0.9); color: white; border-radius: 4px; padding: 8px 16px; font-size: 14px; z-index: 1000; pointer-events: none;"
      >{{ toast.message }}</div>
    </div>
  `,
};
