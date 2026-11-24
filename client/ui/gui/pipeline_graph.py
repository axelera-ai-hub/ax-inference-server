"""Graph logic of the Pipeline Editor: canvas queries, YAML generation and config loading.

Reads the live canvas (`core.app.state.current_graph`), validates that it forms complete Input -> Model -> Sink chains, and converts it to the server config YAML (`_build_yaml`). The reverse direction rebuilds a canvas from a loaded vision config (`_graph_from_vision_config`).

Note:
    Graph queries read the module-level `current_graph`, which is the shared canvas state, not an argument.
    Validation problems are raised as `ValueError` with a user-facing message.
"""


import copy
import json
import os
import re
from pathlib import Path
from typing import Optional

import yaml

from nicegui import core

from config_schema import ServerConfig
from node_catalog import (
    CORES_PER_DEVICE, DEFAULT_FLUSH_THRES, NODE_CATALOG, UNCONFIGURED_AXNET,
    _SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT, _SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT,
)

# Folder where generated YAML configs are saved.
GENERATED_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), 'generated_configs')

# App-wide state shared with app.py and the compile module.
GLOBAL_SETTINGS: dict = core.app.state.global_settings
current_graph: dict = core.app.state.current_graph

# Injected by configure().
_sync_global_settings_widgets = None


def configure(*, sync_global_settings_widgets) -> None:
    """Inject the callback that refreshes the global-settings widgets after a config is loaded."""
    global _sync_global_settings_widgets
    _sync_global_settings_widgets = sync_global_settings_widgets


def _graph_signature(nodes: list, edges: list) -> tuple:
    """Return a hashable fingerprint of nodes and edges (ids, types, positions, handles, data) for change detection."""
    node_sig = tuple(
        (n.get('id'), n.get('type'), tuple(sorted((n.get('position') or {}).items())),
         json.dumps(n.get('data'), sort_keys=True))
        for n in nodes
    )
    edge_sig = tuple(
        (e.get('id'), e.get('source'), e.get('target'), e.get('sourceHandle'), e.get('targetHandle'),
         json.dumps(e.get('data'), sort_keys=True))
        for e in edges
    )
    return node_sig, edge_sig


def _node_by_id(node_id: str) -> dict | None:
    """Return the canvas node with the given id, or None."""
    return next((n for n in current_graph['nodes'] if n['id'] == node_id), None)


def _predecessors(node_id: str) -> list[str]:
    """Return the source node ids of all edges pointing at the node."""
    return [e['source'] for e in current_graph['edges'] if e['target'] == node_id]


def _node_label(node: dict) -> str:
    """Return a display name for error messages: the node label and id when it has a label, else the id."""
    label = node.get('data', {}).get('label')
    return f"{label} node '{node['id']}'" if label else f"node '{node['id']}'"


def _successors(node_id: str) -> list[str]:
    """Return the target node ids of all edges leaving the node."""
    return [e['target'] for e in current_graph['edges'] if e['source'] == node_id]


def _has_downstream_vllm(node_id: str) -> bool:
    """Return True if any node reachable downstream of the node is a (V/L)LM node."""
    visited = {node_id}
    queue = [node_id]
    while queue:
        current = queue.pop()
        for nxt in _successors(current):
            if nxt in visited:
                continue
            visited.add(nxt)
            node = _node_by_id(nxt)
            if node and node.get('data', {}).get('kind') == 'vllm_vlm':
                return True
            queue.append(nxt)
    return False


def _has_upstream_vllm(node_id: str) -> bool:
    """Return True if any node reachable upstream of the node is a (V/L)LM node."""
    visited = {node_id}
    queue = [node_id]
    while queue:
        current = queue.pop()
        for prev in _predecessors(current):
            if prev in visited:
                continue
            visited.add(prev)
            node = _node_by_id(prev)
            if node and node.get('data', {}).get('kind') == 'vllm_vlm':
                return True
            queue.append(prev)
    return False


def _connected_vllm_nodes() -> list[dict]:
    """Return the (V/L)LM nodes that have at least one incoming edge."""
    return [
        n for n in current_graph['nodes']
        if n.get('data', {}).get('kind') == 'vllm_vlm' and _predecessors(n['id'])
    ]


def _upstream_meta_key_source(node_id: str) -> tuple[str, dict] | None:
    """Find the model node that produces the meta_key a node consumes.

    Walks upstream through single-predecessor links, skipping Filter nodes.

    Returns:
        tuple[str, dict] | None: `(kind, data)` of the first non-filter upstream node, or None when a node on the way does not have exactly one predecessor, the path loops, or a node is missing.
    """
    visited = {node_id}
    current = node_id
    while True:
        preds = _predecessors(current)
        if len(preds) != 1:
            return None
        pred_id = preds[0]
        if pred_id in visited:
            return None
        visited.add(pred_id)
        pred = _node_by_id(pred_id)
        if pred is None:
            return None
        pred_kind = pred.get('data', {}).get('kind')
        if pred_kind == 'filter':
            current = pred_id
            continue
        return pred_kind, pred.get('data', {})


# Node kinds allowed between an Input and a Sink; Track is rejected later by _check_chain_hop_kinds.
CHAIN_HOP_KINDS = {'vision', 'track', 'filter', 'roi'}


def _resolve_all_pipelines() -> list[list[dict]]:
    """Resolve the canvas into one chain per Sink: [input, hop..., sink].

    Inputs that feed a (V/L)LM node and sinks fed by one are ignored. Each chain is followed backwards from its Sink through Vision, Track, Filter and ROI nodes to an Input.

    Returns:
        list[list[dict]]: Node chains, input first.

    Raises:
        ValueError: If a node has the wrong number of links, a chain loops or contains a wrong node type, no complete chain exists, or nodes remain outside every chain.
    """
    inputs = [
        n for n in current_graph['nodes']
        if n.get('data', {}).get('kind') == 'input' and not _has_downstream_vllm(n['id'])
    ]
    hops = [n for n in current_graph['nodes'] if n.get('data', {}).get('kind') in CHAIN_HOP_KINDS]
    sinks = [
        n for n in current_graph['nodes']
        if n.get('data', {}).get('kind') == 'sink' and not _has_upstream_vllm(n['id'])
    ]

    chains: list[list[dict]] = []
    for sink in sinks:
        chain: list[dict] = [sink]
        visited_ids = {sink['id']}
        node = sink
        is_first_hop = True
        while True:
            preds = _predecessors(node['id'])
            if len(preds) != 1:
                raise ValueError(
                    f'{_node_label(node)} must have exactly one incoming link (found {len(preds)}) -- '
                    f'connect exactly one {"Model" if is_first_hop else "node"} to it'
                )
            prev = _node_by_id(preds[0])
            prev_kind = prev.get('data', {}).get('kind') if prev else None
            if prev is None or prev_kind not in CHAIN_HOP_KINDS | {'input'}:
                raise ValueError(f"{_node_label(node)}'s upstream node must be a Model node")
            if prev['id'] in visited_ids:
                raise ValueError(
                    f'{_node_label(prev)} is part of a cycle -- a pipeline chain must be a '
                    'single acyclic path from Input to Sink'
                )
            succs = _successors(prev['id'])
            if len(succs) != 1:
                raise ValueError(
                    f'{_node_label(prev)} must have exactly one outgoing link to a '
                    f'{"Sink" if is_first_hop else "Model"} node (found {len(succs)})'
                )
            chain.insert(0, prev)
            visited_ids.add(prev['id'])
            if prev_kind == 'input':
                break
            node = prev
            is_first_hop = False
        chains.append(chain)

    if not chains:
        raise ValueError('Canvas must have at least one complete Input->Model->Sink chain to generate a config')

    claimed_ids = {n['id'] for chain in chains for n in chain}
    stray = [n for n in (inputs + hops + sinks) if n['id'] not in claimed_ids]
    if stray:
        names = ', '.join(_node_label(n) for n in stray)
        raise ValueError(
            f'Canvas has unconnected or incompletely-wired node(s): {names} -- '
            'every Input/Model/Sink node must be part of a complete Input->Model->Sink chain to generate'
        )

    return chains


def _axnet_catalog_name(axnet_value: str) -> str:
    """Return the model name of an .axnet path: the file name without directories and the `.axnet` suffix."""
    base = axnet_value.rsplit('/', 1)[-1]
    return base[:-len('.axnet')] if base.endswith('.axnet') else base


def _vllm_node_devices(data: dict) -> list[str]:
    """Return the device names of a (V/L)LM node as a list, accepting a comma-separated string, a list, or the legacy single `device`."""
    raw = data.get('devices')
    if isinstance(raw, str):
        devices = [d.strip() for d in raw.split(',') if d.strip()]
    else:
        devices = list(raw or [])
    if not devices and data.get('device'):
        devices = [data['device']]
    return devices


def _node_device_cores_pairs(d: dict) -> list[tuple[int, int]]:
    """Return `(device, cores)` pairs of a node.

    Uses `device_cores` if set, else `devices` with the shared `cores`, else the single `device`; a missing core count becomes 0.
    """
    if d.get('device_cores'):
        return [(int(dc['device']), int(dc.get('cores') or 0)) for dc in d['device_cores']]
    if d.get('devices'):
        cores = int(d.get('cores') or 0)
        return [(int(dev), cores) for dev in d['devices']]
    if d.get('device') is not None:
        return [(int(d['device']), int(d.get('cores') or 0))]
    return []


def _node_device_indices(d: dict) -> list[int]:
    """Return the device indices used by a node."""
    return [dev for dev, _ in _node_device_cores_pairs(d)]


def _claimed_cores(exclude_node_id: str | None = None,
                    exclude_roi_submodel: tuple[str, str] | None = None) -> dict[int, int]:
    """Count the AI cores claimed per device by the Vision and ROI models on the canvas.

    ROI sub-models still at the unconfigured placeholder are not counted.

    Args:
        exclude_node_id (str | None, optional): Node to leave out, usually the one being edited.
        exclude_roi_submodel (tuple[str, str] | None, optional): `(roi_node_id, 'model_a' | 'model_b')` to leave out.

    Returns:
        dict[int, int]: Cores claimed by device index.
    """

    claimed: dict[int, int] = {}
    for n in current_graph['nodes']:
        if n['id'] == exclude_node_id:
            continue
        d = n.get('data', {})
        kind = d.get('kind')
        if kind == 'vision':
            for dev, cores in _node_device_cores_pairs(d):
                claimed[dev] = claimed.get(dev, 0) + cores
        elif kind == 'roi':
            sub_models = [('model_a', d.get('model_a'))]
            if d.get('mode') == 'conditional':
                sub_models.append(('model_b', d.get('model_b')))
            for sub_key, sub in sub_models:
                if not sub or sub.get('axnet') == UNCONFIGURED_AXNET:
                    continue
                if exclude_roi_submodel == (n['id'], sub_key):
                    continue
                for dev, cores in _node_device_cores_pairs(sub):
                    claimed[dev] = claimed.get(dev, 0) + cores
    return claimed


def _sanitize_net_name(node_id: str) -> str:
    """Replace every character other than letters, digits and underscore with an underscore."""
    return re.sub(r'[^A-Za-z0-9_]', '_', node_id)


def _roi_internal_id(roi_node_id: str, suffix: str) -> str:
    """Return the id of an internal ROI graph node, `<sanitized roi id>_<suffix>`."""
    return f'{_sanitize_net_name(roi_node_id)}_{suffix}'


def _hop_graph_id(node: dict) -> str:
    """Return the graph node id of a chain hop: net name or node id for Vision, the roi_iter id for ROI, else the sanitized node id."""
    d = node['data']
    kind = d.get('kind')
    if kind == 'vision':
        return _sanitize_net_name(d.get('net_name') or node['id'])
    if kind == 'roi':
        return _roi_internal_id(node['id'], 'roi_iter')
    return _sanitize_net_name(node['id'])


def _vision_hop(node: dict, next_id: str) -> tuple[str, dict, dict]:
    """Convert a Vision node into its config pieces.

    Args:
        node (dict): Node with Vision data.
        next_id (str): Graph id of the next node.

    Returns:
        tuple[str, dict, dict]: Net name, entry for the `nets` section, and graph node.

    Raises:
        ValueError: If no model has been selected.
    """
    m = node['data']
    net_name = _hop_graph_id(node)
    if not m.get('axnet') or m.get('axnet') == UNCONFIGURED_AXNET:
        raise ValueError(
            f"Node '{net_name}' has no model selected -- open it, pick a model in the "
            "Model (.axnet) dropdown, and close the dialog with Save (not Cancel) before "
            "generating the config."
        )
    if m.get('device_cores'):
        device_cores_pairs = [(int(dc['device']), int(dc.get('cores') or CORES_PER_DEVICE)) for dc in m['device_cores']]
    else:
        cores = int(m.get('cores') or CORES_PER_DEVICE)
        device_cores_pairs = [(dev, cores) for dev in (m.get('devices') or [int(m.get('device') or 0)])]
    net_entry = {
        'axnet': m.get('axnet') or '',
        'axnet_config': ';'.join(
            f'net-{idx};devices:{dev}-{c}' for idx, (dev, c) in enumerate(device_cores_pairs)
        ),
    }
    if m.get('labels_file'):
        net_entry['labels_file'] = m['labels_file']
    if m.get('meta_key_override'):
        net_entry['meta_key_override'] = m['meta_key_override']
    net_node = {'id': net_name, 'type': 'net', 'net': net_name, 'next': next_id}
    if m.get('queue_depth') not in (None, ''):
        net_node['queue_depth'] = int(m['queue_depth'])
    if m.get('queue_timeout_ms') not in (None, ''):
        net_node['queue_timeout_ms'] = int(m['queue_timeout_ms'])
    return net_name, net_entry, net_node


def _filter_hop(node: dict, next_id: str) -> dict:
    """Convert a Filter node into a config graph node; unset or blank options are omitted and `which: all` is the default."""
    d = node['data']
    filter_node = {'id': _hop_graph_id(node), 'type': 'filter', 'meta_key': d.get('meta_key') or 'detections',
                   'next': next_id}
    classes_raw = d.get('classes')
    if classes_raw not in (None, ''):
        filter_node['classes'] = [int(c.strip()) for c in str(classes_raw).split(',') if c.strip()]
    if d.get('min_score') not in (None, ''):
        filter_node['min_score'] = float(d['min_score'])
    if d.get('max_score') not in (None, ''):
        filter_node['max_score'] = float(d['max_score'])
    if d.get('min_width') not in (None, ''):
        filter_node['min_width'] = int(d['min_width'])
    if d.get('min_height') not in (None, ''):
        filter_node['min_height'] = int(d['min_height'])
    if d.get('top_k') not in (None, ''):
        filter_node['top_k'] = int(d['top_k'])
    if d.get('which') and d['which'] != 'all':
        filter_node['which'] = d['which']
    return filter_node


def _roi_predicate_dict(predicate: dict) -> dict:
    """Convert the ROI predicate fields into a config predicate (`meta_key_exists`, `kpts_conf_gt` or `expr`).

    Raises:
        ValueError: If the `expr` inputs are not valid JSON.
    """
    ptype = predicate.get('type') or 'meta_key_exists'
    if ptype == 'kpts_conf_gt':
        indices_raw = predicate.get('indices')
        indices = [int(x.strip()) for x in str(indices_raw or '').split(',') if x.strip()]
        return {
            'type': 'kpts_conf_gt',
            'meta_key': predicate.get('meta_key') or '',
            'indices': indices,
            'value': float(predicate.get('value') or 0.0),
        }
    if ptype == 'expr':
        inputs_raw = predicate.get('inputs_json') or '{}'
        try:
            inputs = json.loads(inputs_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Predicate '{predicate.get('name') or '(unnamed)'}': inputs isn't valid JSON ({exc})")
        return {'type': 'expr', 'inputs': inputs, 'body': predicate.get('body') or ''}
    return {'type': 'meta_key_exists', 'meta_key': predicate.get('meta_key') or ''}


def _roi_fragment(roi_node: dict, next_id: str) -> tuple[dict[str, dict], list[dict], dict[str, dict], str]:
    """Expand an ROI node into its fixed set of config graph nodes.

    Builds roi_iter, Model A, an optional condition and Model B (conditional mode), roi_collect and loop_guard, plus the `_roi_done` predicate that ends the loop.

    Args:
        roi_node (dict): The ROI canvas node.
        next_id (str): Graph id the loop exits to.

    Returns:
        tuple: `(nets, graph_nodes, predicates, entry_id)` where `entry_id` is the roi_iter id.

    Raises:
        ValueError: If Model A and Model B resolve to the same net name, or the predicate is invalid.
    """
    d = roi_node['data']
    roi_id = roi_node['id']
    mode = d.get('mode', 'simple')
    model_a = d.get('model_a') or {}
    model_b = d.get('model_b') or {}
    predicate = d.get('predicate') or {}

    iter_id = _roi_internal_id(roi_id, 'roi_iter')
    collect_id = _roi_internal_id(roi_id, 'roi_collect')
    guard_id = _roi_internal_id(roi_id, 'loop_guard')
    gate_id = _roi_internal_id(roi_id, 'gate')
    roi_done_name = _roi_internal_id(roi_id, 'roi_done')

    nets: dict[str, dict] = {}
    predicates: dict[str, dict] = {roi_done_name: {'type': 'meta_key_exists', 'meta_key': '_roi_done'}}
    graph_nodes: list[dict] = []

    det_meta_key = d.get('det_meta_key') or 'detections'

    model_a_node = {'id': _roi_internal_id(roi_id, 'model_a'), 'data': {**model_a, 'kind': 'vision'}}
    a_next = gate_id if mode == 'conditional' else collect_id
    net_name_a, net_entry_a, net_node_a = _vision_hop(model_a_node, a_next)
    nets[net_name_a] = net_entry_a

    roi_iter_node = {
        'id': iter_id, 'type': 'roi_iter', 'meta_key': det_meta_key,
        'next': net_name_a, 'skip_to': next_id,
    }
    if d.get('crop_padding') not in (None, '', 0, 0.0):
        roi_iter_node['crop_padding'] = float(d['crop_padding'])
    graph_nodes.append(roi_iter_node)
    graph_nodes.append(net_node_a)

    cls_meta_key_a = model_a.get('meta_key_override') or model_a.get('cls_meta_key') or 'keypoint_detections'
    if mode == 'conditional':
        predicate_name = _roi_internal_id(roi_id, predicate.get('name') or 'gate_predicate')
        predicates[predicate_name] = _roi_predicate_dict(predicate)

        model_b_node = {'id': _roi_internal_id(roi_id, 'model_b'), 'data': {**model_b, 'kind': 'vision'}}
        net_name_b, net_entry_b, net_node_b = _vision_hop(model_b_node, collect_id)
        if net_name_b == net_name_a:
            raise ValueError(f"{_node_label(roi_node)}: Model A and Model B both resolve to net name "
                              f"'{net_name_a}' -- give one a distinct net_name")
        nets[net_name_b] = net_entry_b

        graph_nodes.append({
            'id': gate_id, 'type': 'condition', 'predicate': predicate_name,
            'then': net_name_b, 'else': collect_id,
        })
        graph_nodes.append(net_node_b)

        cls_meta_key_b = model_b.get('meta_key_override') or model_b.get('cls_meta_key') or 'face_detections'
        collect_cls_meta_key = [cls_meta_key_a, cls_meta_key_b]
    else:
        collect_cls_meta_key = cls_meta_key_a

    graph_nodes.append({
        'id': collect_id, 'type': 'roi_collect', 'det_meta_key': det_meta_key,
        'cls_meta_key': collect_cls_meta_key, 'next': guard_id,
    })
    loop_guard_node = {
        'id': guard_id, 'type': 'loop_guard', 'until': roi_done_name,
        'continue_to': iter_id, 'exit_to': next_id, 'max_iters': int(d.get('max_iters') or 50),
    }
    if d.get('dispatch_queue_depth') is not None:
        loop_guard_node['dispatch_queue_depth'] = int(d['dispatch_queue_depth'])
    graph_nodes.append(loop_guard_node)

    return nets, graph_nodes, predicates, iter_id


def _read_axnet_default_meta_key(axnet_path: str) -> Optional[str]:
    """Read the default postprocess meta_key from a compiled .axnet file.

    Args:
        axnet_path (str): Path, may contain environment variables.

    Returns:
        str | None: The value after `meta_key:` on the first `postprocess*_options=` line that has one, or None if the file or key is missing.
    """
    path = Path(os.path.expandvars(axnet_path))
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if not line.startswith('postprocess') or '_options=' not in line:
            continue
        if 'meta_key:' not in line:
            continue
        _, _, rest = line.partition('meta_key:')
        value, sep, _ = rest.partition(';')
        if not sep:
            continue
        return value
    return None


def _check_meta_key_collisions(nets: dict[str, dict]) -> None:
    """Check that no two nets produce the same meta_key.

    The effective key is the override or the .axnet default; nets whose key is unknown are skipped.

    Raises:
        ValueError: If two nets share a key.
    """
    effective: dict[str, str] = {}
    for net_name, net_entry in nets.items():
        override = net_entry.get('meta_key_override')
        key = override or _read_axnet_default_meta_key(net_entry.get('axnet') or '')
        if key is None:
            continue
        if key in effective:
            other = effective[key]
            raise ValueError(
                f"Nets '{other}' and '{net_name}' both resolve to postprocess meta_key '{key}' -- "
                f"set a distinct meta_key_override on one of them (they'd otherwise silently clobber "
                f"each other's output in frame->meta)"
            )
        effective[key] = net_name


def _vision_fragment(chain: list[dict]) -> tuple[dict[str, dict], str, dict, dict[str, dict]]:
    """Convert one Input -> hops -> Sink chain into config pieces.

    Checks that Filter and ROI meta_keys match the upstream model's output key, that net and predicate names are unique, and that only Vision, Filter and ROI hops are present. ROI chains decode to BGR, others to I420. Optional Input settings (taskset_cpus, membind, imdecode_threads) are written when set; flush_thres and the image-decode queue depth and timeout only when they differ from their defaults.

    Args:
        chain (list[dict]): Input node, hop nodes, Sink node.

    Returns:
        tuple: `(nets, pipeline_id, pipeline_entry, predicates)`.

    Raises:
        ValueError: On name clashes, meta_key mismatches or unsupported node kinds.
    """
    input_node, *middle, sink = chain
    i = input_node['data']

    nets: dict[str, dict] = {}
    predicates: dict[str, dict] = {}
    graph_nodes: list[dict] = []
    entry_id = None
    contains_roi = any(hop['data'].get('kind') == 'roi' for hop in middle)
    current_meta_key: Optional[str] = None
    for idx, hop in enumerate(middle):
        next_id = 'sink' if idx == len(middle) - 1 else _hop_graph_id(middle[idx + 1])
        hop_kind = hop['data'].get('kind')
        if hop_kind == 'vision':
            net_name, net_entry, net_node = _vision_hop(hop, next_id)
            if net_name in nets:
                raise ValueError(f"Two Model nodes both resolve to net name '{net_name}' -- give one a distinct net_name")
            nets[net_name] = net_entry
            graph_nodes.append(net_node)
            graph_id = net_name
            current_meta_key = net_entry.get('meta_key_override') or _read_axnet_default_meta_key(net_entry.get('axnet') or '')
        elif hop_kind == 'filter':
            filter_node = _filter_hop(hop, next_id)
            if current_meta_key is not None and filter_node['meta_key'] != current_meta_key:
                raise ValueError(
                    f"{_node_label(hop)}: meta_key '{filter_node['meta_key']}' doesn't match its upstream "
                    f"model's output meta_key '{current_meta_key}' -- click the refresh icon on the Filter "
                    f"node, or set meta_key to '{current_meta_key}'"
                )
            graph_nodes.append(filter_node)
            graph_id = filter_node['id']
        elif hop_kind == 'roi':
            det_meta_key = hop['data'].get('det_meta_key') or 'detections'
            if current_meta_key is not None and det_meta_key != current_meta_key:
                raise ValueError(
                    f"{_node_label(hop)}: det_meta_key '{det_meta_key}' doesn't match its upstream "
                    f"model's output meta_key '{current_meta_key}' -- open the ROI node and set "
                    f"det_meta_key to '{current_meta_key}'"
                )
            roi_nets, roi_graph_nodes, roi_predicates, roi_entry_id = _roi_fragment(hop, next_id)
            for net_name, net_entry in roi_nets.items():
                if net_name in nets:
                    raise ValueError(f"Two Model nodes both resolve to net name '{net_name}' -- give one a distinct net_name")
                nets[net_name] = net_entry
            for pred_name, pred_entry in roi_predicates.items():
                if pred_name in predicates:
                    raise ValueError(f"Two ROI nodes both resolve to predicate name '{pred_name}' -- "
                                      "give one of them a distinct canvas id")
                predicates[pred_name] = pred_entry
            graph_nodes.extend(roi_graph_nodes)
            graph_id = roi_entry_id
            if (hop['data'].get('mode') or 'simple') == 'conditional':
                final_model = hop['data'].get('model_b') or {}
                current_meta_key = final_model.get('meta_key_override') or final_model.get('cls_meta_key') or 'face_detections'
            else:
                final_model = hop['data'].get('model_a') or {}
                current_meta_key = final_model.get('meta_key_override') or final_model.get('cls_meta_key') or 'keypoint_detections'
        else:
            raise ValueError(f"{_node_label(hop)}: node kind '{hop_kind}' isn't supported inside a Vision chain yet")
        if idx == 0:
            entry_id = graph_id
    graph_nodes.append({'id': 'sink', 'type': 'sink'})

    pipeline_id = i.get('pipeline_id') or entry_id
    pipeline_entry = {
        'id': pipeline_id,
        'interface': 'grpc',
        'port': int(i.get('port') or 50060),
        'im_decode_output_format': 'BGR' if contains_roi else 'I420',
        'timeout': int(i.get('timeout') or 60),
        'graph': {
            'entry': entry_id,
            'nodes': graph_nodes,
        },
    }
    if i.get('taskset_cpus'):
        pipeline_entry['taskset_cpus'] = i['taskset_cpus']
    if i.get('membind') not in (None, ''):
        pipeline_entry['membind'] = int(i['membind'])
    if i.get('flush_thres', DEFAULT_FLUSH_THRES) not in (None, '') \
            and int(i.get('flush_thres', DEFAULT_FLUSH_THRES)) != DEFAULT_FLUSH_THRES:
        pipeline_entry['flush_thres'] = int(i['flush_thres'])
    if i.get('imdecode_threads') not in (None, ''):
        pipeline_entry['imdecode_threads'] = int(i['imdecode_threads'])
    if i.get('imdecode_queue_depth', _SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT) not in (None, '') \
            and int(i.get('imdecode_queue_depth', _SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT)) != _SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT:
        pipeline_entry['imdecode_queue_depth'] = int(i['imdecode_queue_depth'])
    if i.get('imdecode_queue_timeout_ms', _SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT) not in (None, '') \
            and int(i.get('imdecode_queue_timeout_ms', _SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT)) != _SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT:
        pipeline_entry['imdecode_queue_timeout_ms'] = int(i['imdecode_queue_timeout_ms'])
    return nets, pipeline_id, pipeline_entry, predicates


def _vision_global_section(input_nodes: list[dict]) -> dict:
    """Build the config `global` section from the app settings and the Input nodes.

    `watchdog_timeout_ms` and `result_queue_depth` are document-wide, so all Input nodes that set them must agree.

    Raises:
        ValueError: If Input nodes disagree on one of those values.
    """
    g = GLOBAL_SETTINGS
    global_section = {
        'use_axinference_net_opencl': '--enable-opencl' if g['use_axinference_net_opencl'] else '--disable-opencl',
        'use_simd_decode': 1 if g['use_simd_decode'] else 0,
        'restart_interval': int(g.get('restart_interval') or 0),
    }
    if g.get('pipeline_depth') not in (None, ''):
        global_section['pipeline_depth'] = int(g['pipeline_depth'])

    def _agree(field: str, falsy=(None, '', 0)):
        """Return the common non-empty integer value of a field across the Input nodes, or None if none set it."""
        values = {int(i['data'][field]) for i in input_nodes if i['data'].get(field) not in falsy}
        if len(values) > 1:
            raise ValueError(
                f"Input nodes disagree on '{field}' ({sorted(values)}) -- it's a document-wide setting "
                'shared by every pipeline, so every Input node must either leave it unset or agree on the same value'
            )
        return next(iter(values), None)

    watchdog = _agree('watchdog_timeout_ms')
    if watchdog:
        global_section['watchdog_timeout_ms'] = watchdog
    result_queue_depth = _agree('result_queue_depth')
    if result_queue_depth is not None:
        global_section['result_queue_depth'] = result_queue_depth
    return global_section


# Matches one `devices:<id>[,<id>...]-<cores>` segment of an axnet_config string.
_AXNET_CONFIG_SEGMENT_RE = re.compile(r'devices:(\d+(?:,\d+)*)-(\d+)')


def _parse_axnet_config_all(axnet_config: str) -> list[tuple[int, int]]:
    """Parse every `devices:<ids>-<cores>` segment of an axnet_config string into `(device, cores)` pairs."""
    pairs: list[tuple[int, int]] = []
    for seg in _AXNET_CONFIG_SEGMENT_RE.finditer(axnet_config or ''):
        cores = int(seg.group(2))
        pairs.extend((int(dev), cores) for dev in seg.group(1).split(','))
    return pairs


def _parse_axnet_config(axnet_config: str) -> tuple[int, int]:
    """Return the first `(device, cores)` pair of an axnet_config string.

    Not called anywhere in the repository at present.

    Raises:
        ValueError: If no pair can be parsed.
    """
    pairs = _parse_axnet_config_all(axnet_config)
    if not pairs:
        raise ValueError(f"Can't parse device/cores from axnet_config={axnet_config!r}")
    return pairs[0]


def _model_vision_data(net_name: str, net_node_cfg: dict, nets: dict, pipeline_label: str) -> dict:
    """Build Vision node data from a net entry of a loaded config.

    Raises:
        ValueError: If the net is undefined or its axnet_config cannot be parsed.
    """
    if net_name not in nets:
        raise ValueError(f"{pipeline_label} references undefined net '{net_name}'")
    net_entry = nets[net_name]
    pairs = _parse_axnet_config_all(net_entry.get('axnet_config', ''))
    if not pairs:
        raise ValueError(f"{pipeline_label}'s net '{net_name}' has an unparseable axnet_config="
                          f"{net_entry.get('axnet_config')!r}")
    device, cores = pairs[0]
    return {
        'net_name': net_name,
        'axnet': net_entry.get('axnet') or '',
        'device': device,
        'cores': cores,
        'device_cores': [{'device': dev, 'cores': c} for dev, c in pairs],
        'labels_file': net_entry.get('labels_file'),
        'meta_key_override': net_entry.get('meta_key_override'),
        'queue_depth': net_node_cfg.get('queue_depth'),
        'queue_timeout_ms': net_node_cfg.get('queue_timeout_ms'),
    }


def _filter_cfg_to_data(cfg: dict) -> dict:
    """Convert a config filter node into Filter node data (classes become a comma-separated string)."""
    data = {**copy.deepcopy(NODE_CATALOG['model-filter']['data']), 'meta_key': cfg.get('meta_key') or 'detections'}
    if cfg.get('classes') is not None:
        data['classes'] = ','.join(str(c) for c in cfg['classes'])
    for key in ('min_score', 'max_score', 'min_width', 'min_height', 'top_k'):
        if cfg.get(key) is not None:
            data[key] = cfg[key]
    if cfg.get('which'):
        data['which'] = cfg['which']
    return data


def _predicate_to_roi_dict(name: str, pred_entry: dict) -> dict:
    """Convert a config predicate into the ROI node `predicate` fields."""
    ptype = pred_entry.get('type') or 'meta_key_exists'
    data = {**copy.deepcopy(NODE_CATALOG['model-roi']['data']['predicate']), 'name': name, 'type': ptype}
    if ptype == 'kpts_conf_gt':
        data['meta_key'] = pred_entry.get('meta_key')
        data['indices'] = ','.join(str(x) for x in pred_entry.get('indices') or [])
        data['value'] = pred_entry.get('value')
    elif ptype == 'expr':
        data['inputs_json'] = json.dumps(pred_entry.get('inputs') or {})
        data['body'] = pred_entry.get('body')
    else:
        data['meta_key'] = pred_entry.get('meta_key')
    return data


def _try_collapse_roi_skeleton(by_id: dict[str, dict], roi_iter_node: dict, nets: dict, predicates: dict,
                                pipeline_label: str) -> Optional[tuple[dict, str]]:
    """Recognise the fixed ROI node layout produced by `_roi_fragment` and turn it back into one ROI node's data.

    Args:
        by_id (dict[str, dict]): Config graph nodes by id.
        roi_iter_node (dict): The roi_iter node that starts the skeleton.
        nets (dict): Config `nets` section.
        predicates (dict): Config `predicates` section.
        pipeline_label (str): Pipeline name for error messages.

    Returns:
        tuple[dict, str] | None: ROI node data and the id the loop exits to, or None if the nodes do not match the skeleton exactly.
    """
    iter_id = roi_iter_node['id']
    net_name_a = roi_iter_node.get('next')
    node_a = by_id.get(net_name_a)
    if node_a is None or node_a.get('type') != 'net':
        return None

    second_id = node_a.get('next')
    second_node = by_id.get(second_id)
    if second_node is None:
        return None

    net_name_b = None
    node_b = None
    predicate_name = None
    if second_node.get('type') == 'roi_collect':
        mode = 'simple'
        collect_id = second_id
        collect_node = second_node
    elif second_node.get('type') == 'condition':
        mode = 'conditional'
        gate_node = second_node
        predicate_name = gate_node.get('predicate')
        net_name_b = gate_node.get('then')
        collect_id = gate_node.get('else')
        node_b = by_id.get(net_name_b)
        collect_node = by_id.get(collect_id)
        if (node_b is None or node_b.get('type') != 'net' or node_b.get('next') != collect_id
                or collect_node is None or collect_node.get('type') != 'roi_collect'
                or predicate_name not in predicates):
            return None
    else:
        return None

    guard_id = collect_node.get('next')
    guard_node = by_id.get(guard_id)
    if guard_node is None or guard_node.get('type') != 'loop_guard':
        return None
    if guard_node.get('continue_to') != iter_id:
        return None
    exit_to = guard_node.get('exit_to')
    if exit_to is None or roi_iter_node.get('skip_to') != exit_to:
        return None
    roi_done_pred = predicates.get(guard_node.get('until'))
    if roi_done_pred != {'type': 'meta_key_exists', 'meta_key': '_roi_done'}:
        return None

    cls_meta_key = collect_node.get('cls_meta_key')
    if mode == 'conditional':
        if not (isinstance(cls_meta_key, list) and len(cls_meta_key) == 2):
            return None
        cls_meta_key_a, cls_meta_key_b = cls_meta_key
    else:
        if isinstance(cls_meta_key, list):
            return None
        cls_meta_key_a, cls_meta_key_b = cls_meta_key, None

    model_a_data = {**_model_vision_data(net_name_a, node_a, nets, pipeline_label), 'cls_meta_key': cls_meta_key_a}
    if mode == 'conditional':
        model_b_data = {**_model_vision_data(net_name_b, node_b, nets, pipeline_label), 'cls_meta_key': cls_meta_key_b}
        roi_prefix = iter_id[:-len('_roi_iter')] if iter_id.endswith('_roi_iter') else None
        pred_display_name = predicate_name
        if roi_prefix and predicate_name.startswith(roi_prefix + '_'):
            pred_display_name = predicate_name[len(roi_prefix) + 1:]
        predicate_data = _predicate_to_roi_dict(pred_display_name, predicates[predicate_name])
    else:
        model_b_data = copy.deepcopy(NODE_CATALOG['model-roi']['data']['model_b'])
        predicate_data = copy.deepcopy(NODE_CATALOG['model-roi']['data']['predicate'])

    roi_data = {
        **copy.deepcopy(NODE_CATALOG['model-roi']['data']),
        'det_meta_key': roi_iter_node.get('meta_key') or 'detections',
        'crop_padding': roi_iter_node.get('crop_padding', 0.0),
        'max_iters': guard_node.get('max_iters', 50),
        'dispatch_queue_depth': guard_node.get('dispatch_queue_depth'),
        'mode': mode,
        'model_a': model_a_data,
        'model_b': model_b_data,
        'predicate': predicate_data,
    }
    return roi_data, exit_to


def _walk_pipeline_graph(nodes: list[dict], entry: str, nets: dict, predicates: dict,
                          pipeline_label: str) -> list[dict]:
    """Walk a config pipeline graph from its entry to its sink and return the hops as canvas node kinds and data.

    Args:
        nodes (list[dict]): Config graph nodes.
        entry (str): Id of the first node.
        nets (dict): Config `nets` section.
        predicates (dict): Config `predicates` section.
        pipeline_label (str): Pipeline name for error messages.

    Returns:
        list[dict]: Hops as `{'kind': 'vision' | 'filter' | 'roi', 'data': dict}`.

    Raises:
        ValueError: If there is not exactly one sink, the graph loops or references an unknown node, or contains an unsupported node or ROI shape.
    """
    by_id = {n['id']: n for n in nodes}
    sink_ids = [n['id'] for n in nodes if n.get('type') == 'sink']
    if len(sink_ids) != 1:
        raise ValueError(f'{pipeline_label} has {len(sink_ids)} sink node(s) -- expected exactly 1')
    sink_id = sink_ids[0]

    hops: list[dict] = []
    seen: set[str] = set()
    current = entry
    while current != sink_id:
        if current in seen:
            raise ValueError(f"{pipeline_label}: graph has a cycle at node '{current}'")
        seen.add(current)
        node = by_id.get(current)
        if node is None:
            raise ValueError(f"{pipeline_label}: graph references unknown node '{current}'")
        node_type = node.get('type')
        if node_type == 'net':
            model_data = {
                **copy.deepcopy(NODE_CATALOG['model-vision']['data']),
                **_model_vision_data(node['net'], node, nets, pipeline_label),
            }
            hops.append({'kind': 'vision', 'data': model_data})
            current = node.get('next')
        elif node_type == 'filter':
            hops.append({'kind': 'filter', 'data': _filter_cfg_to_data(node)})
            current = node.get('next')
        elif node_type == 'roi_iter':
            collapsed = _try_collapse_roi_skeleton(by_id, node, nets, predicates, pipeline_label)
            if collapsed is None:
                raise ValueError(
                    f"{pipeline_label}: node '{current}' (roi_iter) doesn't match the fixed ROI "
                    "skeleton this GUI generates -- Load Config can't represent a hand-edited "
                    "roi_iter shape"
                )
            roi_data, exit_to = collapsed
            hops.append({'kind': 'roi', 'data': roi_data})
            current = exit_to
        else:
            raise ValueError(f"{pipeline_label}: node '{current}' has unsupported type '{node_type}' "
                              'for Load Config')
    return hops


def _graph_from_vision_config(raw: dict) -> tuple[list[dict], list[dict]]:
    """Build canvas nodes and edges from a loaded vision config.

    Also writes the config's global settings into `GLOBAL_SETTINGS` and refreshes their widgets. Each pipeline becomes one Input -> hops -> Sink row.

    Args:
        raw (dict): Parsed config.

    Returns:
        tuple[list[dict], list[dict]]: Nodes and edges.

    Raises:
        ValueError: If the config has no pipelines or a pipeline cannot be represented.
    """
    pipelines = raw.get('pipelines') or []
    if not pipelines:
        raise ValueError('This config has no pipelines to load')
    nets = raw.get('nets') or {}
    predicates = raw.get('predicates') or {}
    global_section = raw.get('global') or {}

    GLOBAL_SETTINGS['use_axinference_net_opencl'] = global_section.get('use_axinference_net_opencl') == '--enable-opencl'
    GLOBAL_SETTINGS['use_simd_decode'] = bool(global_section.get('use_simd_decode', 1))
    GLOBAL_SETTINGS['restart_interval'] = int(global_section.get('restart_interval') or 0)
    GLOBAL_SETTINGS['pipeline_depth'] = global_section.get('pipeline_depth')
    _sync_global_settings_widgets()

    nodes: list[dict] = []
    edges: list[dict] = []
    for i, pipeline_entry in enumerate(pipelines):
        pipeline_label = f"Vision pipeline '{pipeline_entry.get('id') or i}'"
        graph_cfg = pipeline_entry.get('graph', {})
        hops = _walk_pipeline_graph(graph_cfg.get('nodes', []), graph_cfg.get('entry'), nets, predicates,
                                     pipeline_label)
        if not hops:
            raise ValueError(f'{pipeline_label} has no hops between its entry and sink')

        row_y = 100 + i * 160
        input_id, sink_id = f'input-{i + 1}', f'sink-{i + 1}'
        input_data = {
            **copy.deepcopy(NODE_CATALOG['source-input']['data']),
            'port': int(pipeline_entry.get('port') or 50060),
            'pipeline_id': pipeline_entry.get('id') or '',
            'timeout': int(pipeline_entry.get('timeout') or 60),
            'watchdog_timeout_ms': int(global_section.get('watchdog_timeout_ms') or 0),
            'result_queue_depth': global_section.get('result_queue_depth'),
            'taskset_cpus': pipeline_entry.get('taskset_cpus'),
            'membind': pipeline_entry.get('membind'),
            'flush_thres': int(pipeline_entry.get('flush_thres', DEFAULT_FLUSH_THRES)),
            'imdecode_threads': pipeline_entry.get('imdecode_threads'),
            'imdecode_queue_depth': int(pipeline_entry.get(
                'imdecode_queue_depth', _SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT)),
            'imdecode_queue_timeout_ms': int(pipeline_entry.get(
                'imdecode_queue_timeout_ms', _SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT)),
        }
        sink_data = copy.deepcopy(NODE_CATALOG['sink-output']['data'])

        nodes.append({'id': input_id, 'type': 'input', 'position': {'x': 50, 'y': row_y},
                      'data': {'label': 'input', **input_data}})

        hop_label = {'vision': lambda d: f"net: {d.get('net_name') or ''}", 'filter': lambda d: 'filter',
                     'roi': lambda d: 'ROI'}
        prev_id = input_id
        for hop_idx, hop in enumerate(hops):
            kind, data = hop['kind'], hop['data']
            hop_id = data['net_name'] if kind == 'vision' else f'{kind}-{i + 1}-{hop_idx + 1}'
            nodes.append({
                'id': hop_id, 'position': {'x': 50 + (hop_idx + 1) * 200, 'y': row_y},
                'data': {'label': hop_label[kind](data), **data},
            })
            edges.append({'id': f'{prev_id}->{hop_id}', 'source': prev_id, 'target': hop_id})
            prev_id = hop_id

        nodes.append({'id': sink_id, 'type': 'output', 'position': {'x': 50 + (len(hops) + 1) * 200, 'y': row_y},
                      'data': {'label': 'sink', **sink_data}})
        edges.append({'id': f'{prev_id}->{sink_id}', 'source': prev_id, 'target': sink_id})
    return nodes, edges


def _sanitize_config_filename(name: str) -> str:
    """Reduce a user-typed name to a safe file name inside the config folder.

    Strips directories and adds `.yaml` unless the name ends in `.yaml` or `.yml`.

    Raises:
        ValueError: If the name is empty.
    """
    name = os.path.basename((name or '').strip())
    if not name:
        raise ValueError('File name must not be empty')
    if not name.endswith(('.yaml', '.yml')):
        name += '.yaml'
    return name


def _check_chain_hop_kinds(chain: list[dict]) -> None:
    """Reject chains that contain Track nodes.

    Raises:
        ValueError: If a hop is a Track node.
    """
    middle = chain[1:-1]
    hop_kinds = {hop['data'].get('kind') for hop in middle}
    if 'track' in hop_kinds:
        raise ValueError("Track nodes aren't supported by config generation yet -- no matching config schema exists for them")


def _build_yaml() -> tuple[str, str, str]:
    """Generate the server config YAML from the canvas.

    Resolves all chains, converts each, checks that net names, predicate names, pipeline ids and ports are unique, and validates the result with `ServerConfig`.

    Returns:
        tuple[str, str, str]: YAML text, document id (the pipeline id, or `<first id>_plus<N>` for several pipelines), and pipeline kind ('vision').

    Raises:
        ValueError: On any validation problem found while resolving or converting.
    """
    chains = _resolve_all_pipelines()
    for chain in chains:
        _check_chain_hop_kinds(chain)
    kind = 'vision'

    nets: dict[str, dict] = {}
    predicates: dict[str, dict] = {}
    pipelines: list[dict] = []
    seen_ports: dict[int, str] = {}
    for chain in chains:
        new_nets, pipeline_id, pipeline_entry, new_predicates = _vision_fragment(chain)
        _check_meta_key_collisions(new_nets)
        for net_name, net_entry in new_nets.items():
            if net_name in nets:
                raise ValueError(f"Two Model nodes both resolve to net name '{net_name}' -- give one a distinct net_name")
            nets[net_name] = net_entry
        for pred_name, pred_entry in new_predicates.items():
            if pred_name in predicates:
                raise ValueError(f"Two ROI nodes both resolve to predicate name '{pred_name}' -- "
                                  "give one of them a distinct canvas id")
            predicates[pred_name] = pred_entry
        if pipeline_id in {p['id'] for p in pipelines}:
            raise ValueError(f"Two pipelines both use id '{pipeline_id}' -- give one of them a distinct Pipeline id")
        port = pipeline_entry['port']
        if port in seen_ports:
            raise ValueError(
                f"Pipelines '{seen_ports[port]}' and '{pipeline_id}' both use port {port} -- "
                'give each Input node a distinct port'
            )
        pipelines.append(pipeline_entry)
        seen_ports[port] = pipeline_id

    raw = {
        'global': _vision_global_section([chain[0] for chain in chains]),
        'nets': nets,
    }
    if predicates:
        raw['predicates'] = predicates
    raw['pipelines'] = pipelines
    ServerConfig.model_validate(copy.deepcopy(raw))

    if len(pipelines) == 1:
        doc_id = pipelines[0]['id']
    else:
        doc_id = f"{pipelines[0]['id']}_plus{len(pipelines) - 1}"
    return yaml.safe_dump(raw, sort_keys=False, default_flow_style=False), doc_id, kind


def _save_yaml(text: str, filename: str) -> str:
    """Write YAML text into the generated-configs folder.

    Args:
        text (str): YAML content.
        filename (str): Requested name; sanitized by `_sanitize_config_filename`.

    Returns:
        str: Path of the written file.
    """
    filename = _sanitize_config_filename(filename)
    os.makedirs(GENERATED_CONFIGS_DIR, exist_ok=True)
    out_path = os.path.join(GENERATED_CONFIGS_DIR, filename)
    with open(out_path, 'w') as f:
        f.write(text)
    return out_path
