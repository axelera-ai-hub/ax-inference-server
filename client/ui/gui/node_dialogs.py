"""Node edit dialogs of the Pipeline Editor, opened by double-clicking a node on the canvas.

Provides `_on_node_dblclick` (dialogs for input, vision, (V/L)LM and filter nodes), the ROI sub-canvas dialog, and the shared field and picker helpers also used by `example_wizards.py`.

Note:
    App-level callbacks and the canvas are injected once through `configure()` and used as module globals.
    Unhealthy device indices are shared app-wide through `core.app.state.unhealthy_devices`.
"""


import copy
from typing import Optional

from nicegui import core, ui

from components.pipeline_flow import PipelineFlow
from node_catalog import CORES_PER_DEVICE, DEFAULT_IMDECODE_QUEUE_DEPTH, DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS
from pipeline_graph import (
    _axnet_catalog_name, _claimed_cores, _has_downstream_vllm, _node_by_id, _upstream_meta_key_source,
)

# Shared across modules and page reloads; created once.
if not hasattr(core.app.state, 'unhealthy_devices'):
    core.app.state.unhealthy_devices = set()
_unhealthy_devices: set[int] = core.app.state.unhealthy_devices

# Injected by configure().
flow = None
_check_devices_health_batch = None
_download_prebuilt_model = None
_fetch_devices = None
_fetch_models = None
_fetch_prebuilt_models = None
_fetch_vllm_artifacts = None
_render_detected_meta_key_field = None
_resolve_filter_source_meta_key = None
_update_compile_button = None


def configure(
    *, flow_, check_devices_health_batch, download_prebuilt_model, fetch_devices, fetch_models,
    fetch_prebuilt_models, fetch_vllm_artifacts, render_detected_meta_key_field,
    resolve_filter_source_meta_key, update_compile_button,
) -> None:
    """Inject the canvas and app-level helpers the dialogs depend on.

    Each argument is stored in the module global of the same name (`flow_` becomes `flow`, the others get a leading underscore).
    """
    global flow, _check_devices_health_batch, _download_prebuilt_model, _fetch_devices, _fetch_models
    global _fetch_prebuilt_models, _fetch_vllm_artifacts, _render_detected_meta_key_field
    global _resolve_filter_source_meta_key, _update_compile_button
    flow = flow_
    _check_devices_health_batch = check_devices_health_batch
    _download_prebuilt_model = download_prebuilt_model
    _fetch_devices = fetch_devices
    _fetch_models = fetch_models
    _fetch_prebuilt_models = fetch_prebuilt_models
    _fetch_vllm_artifacts = fetch_vllm_artifacts
    _render_detected_meta_key_field = render_detected_meta_key_field
    _resolve_filter_source_meta_key = resolve_filter_source_meta_key
    _update_compile_button = update_compile_button


def _discovery_fallback_label(base: str, reachable: bool, empty_reason: str) -> str:
    """Build the label for a manual-entry field that replaces a dropdown whose options could not be discovered.

    Args:
        base (str): Field name.
        reachable (bool): Whether the host server answered.
        empty_reason (str): Why the list is empty when the host server is reachable.
    """
    reason = empty_reason if reachable else 'host server unreachable'
    return f'{base} ({reason} -- enter manually)'

def _text_field(widgets: dict, key: str, label: str, value) -> None:
    """Create a text input and store it in `widgets[key]`; None is shown as an empty string."""
    widgets[key] = ui.input(label, value='' if value is None else str(value)) \
        .props('dense outlined').classes('w-full')


def _number_field(widgets: dict, key: str, label: str, value, **props) -> None:
    """Create a number input (extra keyword arguments go to `ui.number`) and store it in `widgets[key]`."""
    widgets[key] = ui.number(label, value=value, **props).props('dense outlined lang=en-US').classes('w-full')


def _collect_widget_values(widgets: dict) -> dict:
    """Read every widget value into a dict; empty text inputs become None."""
    new_data = {}
    for key, w in widgets.items():
        v = w.value
        if isinstance(w, ui.input) and v == '':
            v = None
        new_data[key] = v
    return new_data


class _DynamicValue:
    """A read-only stand-in for a widget whose `value` is computed on access.

    Used so the device and cores picker can expose `widgets['device']` and `widgets['cores']` like real widgets.
    """
    def __init__(self, getter):
        """Store the getter.

        Args:
            getter (Callable): Zero-argument callable returning the current value.
        """
        self._getter = getter

    @property
    def value(self):
        """Return the result of the getter."""
        return self._getter()


def _device_select_options(devices: list[dict], claimed: dict[int, int], cores_needed: int,
                            current_device) -> dict[int, str]:
    """Build dropdown options for devices with enough free cores.

    Not called anywhere in the repository at present.

    A device is listed if it has at least `cores_needed` free cores or is the currently selected one.

    Args:
        devices (list[dict]): Devices with `index` and `name`.
        claimed (dict[int, int]): Cores already claimed per device index.
        cores_needed (int): Cores the model requires.
        current_device: Index of the device already selected, always kept in the list.

    Returns:
        dict[int, str]: Device index to label with the free-core count.
    """
    options: dict[int, str] = {}
    for d in devices:
        idx = d['index']
        free = CORES_PER_DEVICE - claimed.get(idx, 0)
        if free >= cores_needed or idx == current_device:
            options[idx] = f"Device {idx} ({d['name']}) -- {max(free, 0)}/{CORES_PER_DEVICE} cores free"
    return options


def _render_multi_device_cores_picker(data: dict, widgets: dict, devices: list[dict], devices_result: dict,
                                       claimed: dict[int, int]) -> dict[int, ui.number]:
    """Render the device selector and one core-count input per selected device.

    Uses a multi-select of devices when the host server listed any, otherwise a comma-separated text input. Devices with no free cores are reported instead of getting an input. Also sets `widgets['device']` and `widgets['cores']` to dynamic values describing the first selected device.

    Args:
        data (dict): Node data with `device_cores`, or `device` and `cores`, as the initial selection.
        widgets (dict): Widget registry that receives `device` and `cores`.
        devices (list[dict]): Devices with `index` and `name`; may be empty.
        devices_result (dict): Raw device-discovery result; only `reachable` is read.
        claimed (dict[int, int]): Cores already claimed per device index by other models.

    Returns:
        dict[int, ui.number]: Core-count inputs by device index. The dict is updated in place as the selection changes.
    """
    existing_device_cores = data.get('device_cores') or [
        {'device': int(data.get('device', 0)), 'cores': int(data.get('cores') or 4)}
    ]
    cores_by_device: dict[int, int] = {
        int(dc['device']): int(dc.get('cores') or 4) for dc in existing_device_cores
    }
    selected_devices: list[int] = list(cores_by_device.keys())
    device_cores_widgets: dict[int, ui.number] = {}
    device_cores_container_box: dict[str, ui.column] = {}

    def _render_device_cores_fields() -> None:
        """Rebuild the per-device core inputs from the current device selection."""
        device_cores_container = device_cores_container_box['container']
        device_cores_container.clear()
        device_cores_widgets.clear()
        with device_cores_container:
            if not selected_devices:
                ui.label('Select at least one device above.').classes('text-caption text-negative')
            for dev in selected_devices:
                free = max(CORES_PER_DEVICE - claimed.get(dev, 0), 0)
                if free == 0:
                    ui.label(
                        f'Device {dev}: 0/{CORES_PER_DEVICE} cores free -- '
                        'already fully claimed by another model.'
                    ).classes('text-caption text-negative')
                    continue
                default_cores = min(cores_by_device.get(dev, 4), free)
                device_cores_widgets[dev] = ui.number(
                    f'Cores on Device {dev} ({free}/{CORES_PER_DEVICE} free)',
                    value=default_cores, min=1, max=free, format='%.0f',
                ).props('dense outlined').classes('w-full')

    if devices:
        dev_options = {
            d['index']: f"Device {d['index']} ({d['name']}) -- "
                         f"{max(CORES_PER_DEVICE - claimed.get(d['index'], 0), 0)}/{CORES_PER_DEVICE} cores free"
            for d in devices
        }
        for dev in selected_devices:
            dev_options.setdefault(dev, f'Device {dev}')

        def _on_devices_change(e) -> None:
            """Update the selected devices from the multi-select and rebuild the core inputs."""
            nonlocal selected_devices
            selected_devices = [int(v) for v in (e.value or [])]
            _render_device_cores_fields()

        ui.select(
            dev_options, label='Devices (select one or more)', multiple=True, value=list(selected_devices),
        ).props('dense outlined use-chips').classes('w-full').on_value_change(_on_devices_change)
    else:
        ui.label(_discovery_fallback_label(
            'Device index', devices_result.get('reachable', False), 'no devices found via axdevice',
        )).classes('text-caption text-grey')

        def _on_manual_devices_change(e) -> None:
            """Parse the comma-separated device indices (ignored while not valid integers) and rebuild the core inputs."""
            nonlocal selected_devices
            try:
                selected_devices = sorted({
                    int(v.strip()) for v in (e.value or '').split(',') if v.strip() != ''
                })
            except ValueError:
                return
            _render_device_cores_fields()

        ui.input(
            'Device indices (comma-separated, e.g. 0,1)',
            value=','.join(str(dev) for dev in selected_devices),
        ).props('dense outlined').classes('w-full').on_value_change(_on_manual_devices_change)

    device_cores_container_box['container'] = ui.column().classes('w-full gap-1')
    _render_device_cores_fields()

    widgets['device'] = _DynamicValue(
        lambda: selected_devices[0] if selected_devices else int(data.get('device', 0))
    )
    widgets['cores'] = _DynamicValue(
        lambda: int(device_cores_widgets[selected_devices[0]].value)
        if selected_devices and selected_devices[0] in device_cores_widgets
        else int(data.get('cores') or 4)
    )

    return device_cores_widgets


async def _build_axnet_picker(data: dict, widgets: dict, vision_models: list, models_reachable: bool) -> None:
    """Render the model chooser: a checkbox for prebuilt models plus a dropdown or text field for the .axnet path.

    Without the checkbox the dropdown lists vision models found under the SDK build directory. With it, the prebuilt catalog is fetched and picking an entry downloads its artifacts. Falls back to a text field when nothing was discovered. The chosen model is stored in `widgets['axnet']`.

    Args:
        data (dict): Node data; `axnet` and `use_prebuilt_models` give the initial state, and `axnet` is updated after a download.
        widgets (dict): Widget registry that receives `use_prebuilt_models` and `axnet`.
        vision_models (list): Host-server vision models with `name` and `axnet_path`.
        models_reachable (bool): Whether the host server answered when models were listed.
    """
    axnet_container = ui.column().classes('w-full gap-0')
    prebuilt_fetched: set[str] = set()

    def _render_axnet_widget(use_prebuilt: bool, prebuilt_models: list[str] | None = None,
                              prebuilt_reachable: bool = True) -> None:
        """Rebuild the model selector for the prebuilt or the build-directory mode."""
        axnet_container.clear()
        with axnet_container:
            if use_prebuilt:
                if prebuilt_models:
                    options = {m: (f'{m} (downloaded)' if m in prebuilt_fetched else m) for m in prebuilt_models}
                    cur = data.get('axnet')
                    if cur not in options:
                        if cur and ('/' in cur or cur.endswith('.axnet')):
                            options[cur] = f'{_axnet_catalog_name(cur)} (previously downloaded)'
                        else:
                            cur = next(iter(options), None)
                    widgets['axnet'] = ui.select(
                        options, label='Prebuilt model (axdownloadmodel catalog)', value=cur,
                    ).props('dense outlined').classes('w-full')

                    async def _on_prebuilt_model_change(e) -> None:
                        """Download the artifacts of a newly chosen prebuilt model, then mark it downloaded and redraw the selector."""
                        chosen = e.value
                        if not chosen or '/' in chosen or chosen.endswith('.axnet') or chosen in prebuilt_fetched:
                            return
                        spinner = ui.notification(f'Downloading model {chosen}...', spinner=True, timeout=None)
                        result = await _download_prebuilt_model(chosen, artifacts_only=True)
                        spinner.dismiss()
                        if not result.get('reachable', False):
                            ui.notify(f'Could not reach host server to download {chosen} -- '
                                      'compiling/launching this pipeline will likely fail',
                                      type='negative', multi_line=True, timeout=10000)
                            return
                        if result.get('error'):
                            ui.notify(f'Failed to download model {chosen}: {result["error"]}',
                                      type='negative', multi_line=True, timeout=10000)
                            return
                        prebuilt_fetched.add(chosen)
                        data['axnet'] = chosen
                        _render_axnet_widget(True, prebuilt_models, prebuilt_reachable)

                    widgets['axnet'].on_value_change(_on_prebuilt_model_change)
                else:
                    _text_field(widgets, 'axnet', _discovery_fallback_label(
                        'Prebuilt model name', prebuilt_reachable,
                        'no prebuilt models found in catalog',
                    ), data.get('axnet'))
            elif vision_models:
                options = {m['axnet_path']: f"{m['name']}" for m in vision_models}
                cur = data.get('axnet') if data.get('axnet') in options else next(iter(options))
                widgets['axnet'] = ui.select(options, label='Model (.axnet, from host server)', value=cur) \
                    .props('dense outlined').classes('w-full')
            else:
                _text_field(widgets, 'axnet', _discovery_fallback_label(
                    'Model .axnet path', models_reachable,
                    'no vision models found under $SDK_ROOT/build',
                ), data.get('axnet'))

    async def _refresh_prebuilt_models() -> None:
        """Fetch the prebuilt model catalog and show it in the selector."""
        notif = ui.notification('Fetching prebuilt model catalog...', spinner=True, timeout=None)
        result = await _fetch_prebuilt_models()
        notif.dismiss()
        _render_axnet_widget(True, result.get('models', []), result.get('reachable', False))

    async def _on_prebuilt_toggle(e) -> None:
        """Switch the selector between the prebuilt catalog and the build directory when the checkbox changes."""
        if e.value:
            await _refresh_prebuilt_models()
        else:
            _render_axnet_widget(False)

    use_prebuilt_initial = bool(data.get('use_prebuilt_models', False))
    widgets['use_prebuilt_models'] = ui.checkbox(
        'Use prebuilt models (axdownloadmodel catalog instead of build/ dir)',
        value=use_prebuilt_initial,
    )
    widgets['use_prebuilt_models'].on_value_change(_on_prebuilt_toggle)

    if use_prebuilt_initial:
        await _refresh_prebuilt_models()
    else:
        _render_axnet_widget(False)


def _roi_subflow_graph(roi_data: dict) -> tuple[list[dict], list[dict]]:
    """Build the fixed sub-canvas graph of an ROI node.

    Nodes are locked (not deletable or connectable): bridge_in, roi_iter, model_a, roi_collect, loop_guard and bridge_out, plus condition and model_b in conditional mode. Saved positions in `_node_positions` override the default layout.

    Args:
        roi_data (dict): ROI node data (`mode`, `model_a`, `model_b`, `predicate`, `det_meta_key`, `max_iters`, `_node_positions`).

    Returns:
        tuple[list[dict], list[dict]]: Nodes and edges.
    """
    mode = roi_data.get('mode', 'simple')
    model_a = roi_data.get('model_a') or {}
    model_b = roi_data.get('model_b') or {}
    predicate = roi_data.get('predicate') or {}
    saved_positions = roi_data.get('_node_positions') or {}

    def locked_node(node_id: str, kind: str, label: str, x: int, y: int, **extra) -> dict:
        """Create a locked sub-canvas node at the saved position, or at (x, y) when none is saved."""
        return {
            'id': node_id, 'position': saved_positions.get(node_id) or {'x': x, 'y': y},
            'data': {'kind': kind, 'label': label, 'locked': True},
            'deletable': False, 'connectable': False,
            **extra,
        }

    def locked_edge(edge_id: str, source: str, target: str, **extra) -> dict:
        """Create a non-deletable sub-canvas edge."""
        return {'id': edge_id, 'source': source, 'target': target, 'deletable': False, **extra}

    def model_label(prefix: str, model: dict) -> str:
        """Build a two-line node label from a prefix and the model name."""
        name = model.get('net_name') or _axnet_catalog_name(model.get('axnet') or '')
        return f"{prefix}\n{name or '(model unset)'}"

    if mode == 'conditional':
        row1_y, row2_y = 80, 300
        bridge_in_x, roi_iter_x, model_a_x = 0, 230, 425
        condition_x, model_b_x = 625, 850
        collect_x, loop_guard_x, bridge_out_x = 625, 230, 0
    else:
        row1_y, row2_y = 80, 190
        bridge_in_x, roi_iter_x, model_a_x = 0, 235, 480
        collect_x, loop_guard_x, bridge_out_x = 480, 235, 0

    nodes = [
        locked_node('bridge_in', 'roi_bridge', 'Input\n(from outer chain)', bridge_in_x, row1_y, type='input'),
        locked_node('roi_iter', 'roi_iter',
                    f"roi_iter (locked)\nmeta_key: {roi_data.get('det_meta_key') or 'detections'}", roi_iter_x, row1_y),
        locked_node('model_a', 'roi_model_a', model_label('Model A', model_a), model_a_x, row1_y),
    ]
    edges = [
        locked_edge('e_bridge_iter', 'bridge_in', 'roi_iter'),
        locked_edge('e_iter_a', 'roi_iter', 'model_a'),
    ]

    if mode == 'conditional':
        nodes.append(locked_node(
            'condition', 'roi_condition',
            f"condition (locked)\n{predicate.get('name') or 'roi_gate'}: {predicate.get('type') or 'meta_key_exists'}",
            condition_x, row1_y,
        ))
        nodes.append(locked_node('model_b', 'roi_model_b', model_label('Model B', model_b), model_b_x, row1_y))
        edges += [
            locked_edge('e_a_cond', 'model_a', 'condition'),
            locked_edge('e_cond_b', 'condition', 'model_b', label='then'),
            locked_edge('e_b_collect', 'model_b', 'roi_collect'),
            locked_edge('e_cond_collect', 'condition', 'roi_collect', label='else'),
        ]
    else:
        edges.append(locked_edge('e_a_collect', 'model_a', 'roi_collect'))

    nodes.append(locked_node(
        'roi_collect', 'roi_collect', 'roi_collect\n(locked)', collect_x, row2_y,
        targetPosition='right', sourcePosition='left',
    ))
    nodes.append(locked_node(
        'loop_guard', 'roi_loop_guard',
        f"loop_guard (locked)\nmax_iters={roi_data.get('max_iters', 50)}", loop_guard_x, row2_y,
        targetPosition='right', sourcePosition='left',
    ))
    nodes.append(locked_node(
        'bridge_out', 'roi_bridge', 'Sink\n(to outer chain)', bridge_out_x, row2_y, type='output',
        targetPosition='right',
    ))
    edges += [
        locked_edge('e_collect_loop', 'roi_collect', 'loop_guard'),
        locked_edge('e_loop_iter', 'loop_guard', 'roi_iter', label='continue_to'),
        locked_edge('e_loop_out', 'loop_guard', 'bridge_out', label='exit_to'),
    ]
    return nodes, edges


async def _open_roi_subflow_dialog(roi_node_id: str, data: dict) -> None:
    """Open the ROI dialog that shows the ROI skeleton on its own canvas.

    Double-clicking a sub-node opens its settings dialog; the toggle switches between simple and conditional mode. Changes are written back to the ROI node on the main canvas.

    Args:
        roi_node_id (str): Id of the ROI node on the main canvas.
        data (dict): Current data of that node; edited on a deep copy.
    """
    roi_data = copy.deepcopy(data)
    inner_container = None

    def _render_inner() -> None:
        """Rebuild the sub-canvas from the current ROI data."""
        inner_container.clear()
        with inner_container:
            nodes, edges = _roi_subflow_graph(roi_data)
            PipelineFlow(nodes=nodes, edges=edges, on_node_dblclick=_on_roi_subflow_node_dblclick,
                         on_graph_changed=_on_roi_subflow_graph_changed, show_clear_button=False,
                         agent_scope='roi_subflow')

    def _persist_and_rerender() -> None:
        """Write the ROI data to the main canvas node and redraw the sub-canvas."""
        flow.update_node_data(roi_node_id, roi_data)
        _render_inner()

    def _on_roi_subflow_graph_changed(event) -> None:
        """Save sub-node positions into the ROI data and keep the agent copy of the sub-graph up to date."""
        nodes = event.args.get('nodes', [])
        edges = event.args.get('edges', [])
        roi_data['_node_positions'] = {n['id']: n['position'] for n in nodes if n.get('position')}
        flow.update_node_data(roi_node_id, roi_data)
        event.sender.agent_nodes = nodes
        event.sender.agent_edges = edges

    async def _on_roi_subflow_node_dblclick(event) -> None:
        """Open the settings dialog for a double-clicked ROI sub-node (roi_iter, loop_guard, model A/B, condition); bridge and collect nodes only show a notice."""
        sub_data = event.args.get('data', {}) or {}
        sub_kind = sub_data.get('kind')
        if sub_kind == 'roi_bridge':
            ui.notify('This is a fixed connection point to the outer pipeline -- nothing to edit here.')
            return
        if sub_kind == 'roi_collect':
            ui.notify("roi_collect is auto-configured from Model A/B's cls_meta_key and the "
                      'det_meta_key set on roi_iter -- nothing to edit here directly.', multi_line=True)
            return

        widgets: dict = {}

        def field(key: str, label: str, value) -> None:
            """Add a text field to this dialog's widgets."""
            _text_field(widgets, key, label, value)

        def number(key: str, label: str, value, **props) -> None:
            """Add a number field to this dialog's widgets."""
            _number_field(widgets, key, label, value, **props)

        with ui.dialog() as sub_dialog, ui.card().classes('w-96'):
            if sub_kind == 'roi_iter':
                ui.label('Edit roi_iter / roi_collect settings').classes('text-subtitle1 font-semibold')
                with ui.row().classes('w-full items-end gap-1 no-wrap'):
                    widgets['det_meta_key'] = ui.input(
                        'det_meta_key (detections key to iterate/collect, e.g. detections)',
                        value=roi_data.get('det_meta_key', 'detections'),
                    ).props('dense outlined').classes('flex-grow')

                    async def _on_refresh_det_meta_key() -> None:
                        """Fill det_meta_key from the single upstream node of the ROI block."""
                        source = _upstream_meta_key_source(roi_node_id)
                        if source is None:
                            ui.notify('Connect this ROI node to exactly one upstream node first', type='warning')
                            return
                        meta_key = await _resolve_filter_source_meta_key(source, notify=True)
                        if meta_key is None:
                            return
                        widgets['det_meta_key'].value = meta_key
                        ui.notify(f"det_meta_key set to '{meta_key}'", type='positive')

                    ui.button(icon='refresh', on_click=_on_refresh_det_meta_key).props('dense flat round size=sm') \
                        .tooltip('Auto-detect from the node connected to this ROI block\'s input')
                number('crop_padding', 'crop_padding (fraction, 0.0 = none)',
                       roi_data.get('crop_padding', 0.0), min=0, format='%.2f')
            elif sub_kind == 'roi_loop_guard':
                ui.label('Edit loop_guard settings').classes('text-subtitle1 font-semibold')
                number('max_iters', 'max_iters', roi_data.get('max_iters', 50), min=1, format='%.0f')
                number('dispatch_queue_depth', 'dispatch_queue_depth (optional)',
                       roi_data.get('dispatch_queue_depth'), format='%.0f')
            elif sub_kind in ('roi_model_a', 'roi_model_b'):
                model_key = 'model_a' if sub_kind == 'roi_model_a' else 'model_b'
                label = 'Model A' if sub_kind == 'roi_model_a' else 'Model B'
                model_data = roi_data.setdefault(model_key, {})
                ui.label(f'Edit {label}').classes('text-subtitle1 font-semibold')
                loading = ui.notification('Loading model & device info...', spinner=True, timeout=None)
                models = await _fetch_models()
                devices_result = await _fetch_devices()
                devices = devices_result['devices']
                claimed = _claimed_cores(exclude_roi_submodel=(roi_node_id, model_key))
                loading.dismiss()

                field('net_name', 'Network name (optional -- the nets: key in the '
                      'generated YAML; blank = auto-derived)', model_data.get('net_name'))
                await _build_axnet_picker(model_data, widgets, models.get('vision_models', []),
                                          models.get('reachable', False))
                device_cores_widgets = _render_multi_device_cores_picker(
                    model_data, widgets, devices, devices_result, claimed)
                field('labels_file', 'labels_file (optional)', model_data.get('labels_file'))
                field('meta_key_override', "meta_key_override (optional -- set this if this model's "
                      'default postprocess meta_key collides with another net in the same pipeline)',
                      model_data.get('meta_key_override'))
                number('queue_depth', 'queue_depth (optional)', model_data.get('queue_depth'), format='%.0f')
                number('queue_timeout_ms', 'queue_timeout_ms (optional)', model_data.get('queue_timeout_ms'), format='%.0f')
                await _render_detected_meta_key_field(
                    model_data, widgets, 'cls_meta_key',
                    label="cls_meta_key (this model's output meta_key, as referenced by roi_collect)")
            elif sub_kind == 'roi_condition':
                ui.label('Edit condition').classes('text-subtitle1 font-semibold')
                predicate = roi_data.setdefault('predicate', {})
                field('name', 'Predicate name', predicate.get('name', 'roi_gate'))
                widgets['type'] = ui.select(
                    ['meta_key_exists', 'kpts_conf_gt', 'expr'], label='type',
                    value=predicate.get('type') or 'meta_key_exists',
                ).props('dense outlined').classes('w-full')
                fields_container = ui.column().classes('w-full gap-0')

                def _render_meta_key_with_refresh() -> None:
                    """Render the predicate meta_key input with a button that copies it from Model A."""
                    with ui.row().classes('w-full items-end gap-1 no-wrap'):
                        widgets['meta_key'] = ui.input('meta_key', value=predicate.get('meta_key')) \
                            .props('dense outlined').classes('flex-grow')

                        async def _on_refresh_condition_meta_key() -> None:
                            """Set the predicate meta_key from Model A's meta_key_override or cls_meta_key."""
                            model_a = roi_data.get('model_a') or {}
                            cls_meta_key = model_a.get('meta_key_override') or model_a.get('cls_meta_key')
                            if not cls_meta_key:
                                ui.notify("Set Model A's meta_key first (open Model A, use its refresh button)",
                                          type='warning')
                                return
                            widgets['meta_key'].value = cls_meta_key
                            ui.notify(f"meta_key set to '{cls_meta_key}'", type='positive')

                        ui.button(icon='refresh', on_click=_on_refresh_condition_meta_key) \
                            .props('dense flat round size=sm') \
                            .tooltip("Auto-detect from this ROI block's Model A")

                def _render_predicate_fields(ptype: str) -> None:
                    """Rebuild the predicate fields for the chosen predicate type."""
                    fields_container.clear()
                    for k in ('meta_key', 'indices', 'value', 'inputs_json', 'body'):
                        widgets.pop(k, None)
                    with fields_container:
                        if ptype == 'meta_key_exists':
                            _render_meta_key_with_refresh()
                        elif ptype == 'kpts_conf_gt':
                            _render_meta_key_with_refresh()
                            field('indices', 'indices (comma-separated, e.g. 0,1,2)', predicate.get('indices'))
                            number('value', 'value (confidence threshold)', predicate.get('value'), format='%.3f')
                        elif ptype == 'expr':
                            field('inputs_json', 'inputs (JSON object mapping var name -> accessor expr)',
                                  predicate.get('inputs_json'))
                            field('body', 'body (expression)', predicate.get('body'))

                widgets['type'].on_value_change(lambda e: _render_predicate_fields(e.value))
                _render_predicate_fields(predicate.get('type') or 'meta_key_exists')
            else:
                ui.label('This node type has no editable config.').classes('text-grey')

            def _save() -> None:
                """Merge the dialog values into the ROI data, close the dialog and refresh the sub-canvas."""
                if sub_kind in ('roi_iter', 'roi_loop_guard'):
                    roi_data.update(_collect_widget_values(widgets))
                elif sub_kind in ('roi_model_a', 'roi_model_b'):
                    model_key = 'model_a' if sub_kind == 'roi_model_a' else 'model_b'
                    roi_data[model_key] = {**roi_data.get(model_key, {}), **_collect_widget_values(widgets)}
                    roi_data[model_key]['device_cores'] = [
                        {'device': dev, 'cores': int(w.value)} for dev, w in device_cores_widgets.items()
                    ]
                elif sub_kind == 'roi_condition':
                    roi_data['predicate'] = {**roi_data.get('predicate', {}), **_collect_widget_values(widgets)}
                sub_dialog.close()
                _persist_and_rerender()

            with ui.row().classes('w-full justify-end q-mt-md'):
                ui.button('Cancel', on_click=sub_dialog.close).props('flat')
                if widgets:
                    ui.button('Save', on_click=_save)
        sub_dialog.open()

    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 1200px'):
        ui.label(f"ROI: {roi_node_id}").classes('text-subtitle1 font-semibold')
        ui.label(
            'Double-click a node below to edit it. The skeleton wiring itself '
            '(roi_iter -> ... -> roi_collect -> loop_guard) is fixed and cannot '
            'be rewired or deleted.'
        ).classes('text-caption text-grey')

        def _on_mode_toggle(e) -> None:
            """Switch the ROI between simple and conditional mode and reset the saved node positions."""
            roi_data['mode'] = 'conditional' if e.value else 'simple'
            roi_data['_node_positions'] = {}
            _persist_and_rerender()

        ui.switch('Conditional (gate a second model)', value=roi_data.get('mode') == 'conditional') \
            .on_value_change(_on_mode_toggle)
        inner_container = ui.column().classes('w-full gap-0')

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Close', on_click=dialog.close)
    dialog.on('show', _render_inner)
    dialog.open()


async def _on_node_dblclick(event) -> None:
    """Open the edit dialog for a double-clicked node on the main canvas.

    The dialog depends on `data['kind']`: input, vision, vllm_vlm and filter nodes have fields, ROI nodes open the sub-canvas dialog, and other kinds show a notice. Host-server model, artifact and device lists are fetched first where needed. Save merges the field values into the node data on the canvas.

    Args:
        event: NiceGUI event whose args hold the node `id` and `data`.
    """
    node_id = event.args['id']
    data = event.args.get('data', {}) or {}
    node = _node_by_id(node_id)
    if node is None:
        return
    kind = data.get('kind')
    widgets: dict = {}

    def field(key: str, label: str, value) -> None:
        """Add a text field to this dialog's widgets."""
        _text_field(widgets, key, label, value)

    def number(key: str, label: str, value, **props) -> None:
        """Add a number field to this dialog's widgets."""
        _number_field(widgets, key, label, value, **props)

    loading = ui.notification('Loading model & device info...', spinner=True, timeout=None) \
        if kind in ('vision', 'vllm_vlm') else None

    models = await _fetch_models() if kind == 'vision' else {'vision_models': [], 'vlm_models': [], 'reachable': False}
    vllm_artifacts_result = await _fetch_vllm_artifacts() if kind == 'vllm_vlm' else {'artifacts': [], 'reachable': False}
    devices_result = await _fetch_devices() if kind in ('vision', 'vllm_vlm') else {'devices': [], 'reachable': False}
    devices = devices_result['devices']
    claimed = _claimed_cores(exclude_node_id=node_id)

    if loading is not None:
        loading.dismiss()

    if kind == 'roi':
        await _open_roi_subflow_dialog(node_id, data)
        return

    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label(f"Edit {data.get('label', node_id)}").classes('text-subtitle1 font-semibold')
        if kind == 'input':
            feeds_vllm = _has_downstream_vllm(node_id)
            number('port', 'Port', data.get('port', 50060), min=1024, max=65535, format='%.0f')
            ui.label('Interface: grpc (fixed for now)').classes('text-caption text-grey q-mt-sm')
            field('pipeline_id', 'Pipeline id', data.get('pipeline_id'))
            if feeds_vllm:
                ui.label(
                    'Connected to a (V/L)LM node: this is the client request/response '
                    'timeout for chat calls (passed to AxLlmClient/AxVlmClient\'s '
                    'timeout=); every other field below is unused in this mode.'
                ).classes('text-caption text-grey q-mt-sm')
            else:
                ui.label('Used when the upstream model is Vision:').classes('text-caption text-grey q-mt-sm')
            number('timeout', 'timeout (s)', data.get('timeout', 60), min=1, format='%.0f')
            number('watchdog_timeout_ms', 'watchdog_timeout_ms (0 = disabled)',
                   data.get('watchdog_timeout_ms', 0), min=0, format='%.0f')
            number('result_queue_depth', 'result_queue_depth (optional)',
                   data.get('result_queue_depth'), min=1, format='%.0f')
            number('imdecode_threads', 'imdecode_threads override (blank = auto, 4x pinned cores)',
                   data.get('imdecode_threads'), min=1, format='%.0f')
            number('imdecode_queue_depth', 'imdecode_queue_depth',
                   data.get('imdecode_queue_depth', DEFAULT_IMDECODE_QUEUE_DEPTH), min=1, format='%.0f')
            number('imdecode_queue_timeout_ms', 'imdecode_queue_timeout_ms',
                   data.get('imdecode_queue_timeout_ms', DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS),
                   min=0, format='%.0f')
            ui.label(
                'Moved here from the Sink node, which has no attributes of its own '
                '(unused when feeding a (V/L)LM node, disabled above):'
            ).classes('text-caption text-grey q-mt-sm')
            field('taskset_cpus', 'taskset_cpus (optional, e.g. 0-7)', data.get('taskset_cpus'))
            number('membind', 'membind (optional)', data.get('membind'), format='%.0f')
            if feeds_vllm:
                for key in (
                    'port', 'pipeline_id', 'watchdog_timeout_ms', 'result_queue_depth',
                    'imdecode_threads', 'imdecode_queue_depth', 'imdecode_queue_timeout_ms',
                    'taskset_cpus', 'membind',
                ):
                    widgets[key].disable()
        elif kind == 'vision':
            field('net_name', 'Network name (optional -- the nets: key in the '
                  'generated YAML; blank = auto-derived from this node)',
                  data.get('net_name'))
            vision_models = models.get('vision_models', [])
            await _build_axnet_picker(data, widgets, vision_models, models.get('reachable', False))

            device_cores_widgets = _render_multi_device_cores_picker(data, widgets, devices, devices_result, claimed)

            async def _on_refresh_vision_device_health() -> None:
                """Run a health check on the selected devices, update the shared unhealthy set and the Compile button, and notify the result."""
                indices = sorted(device_cores_widgets.keys())
                if not indices:
                    ui.notify('Select at least one device first', type='warning')
                    return
                vision_health_refresh_btn.disable()
                try:
                    result = await _check_devices_health_batch(indices, {})
                    if not result.get('reachable', False):
                        ui.notify('Device health check unavailable (host server unreachable)',
                                  type='warning')
                        return
                    if result.get('error') and not result.get('devices'):
                        ui.notify(f"Device health check failed: {result['error']}", type='warning')
                        return
                    by_index = {d['index']: d for d in result.get('devices', [])}
                    unhealthy = []
                    for idx in indices:
                        info = by_index.get(idx)
                        healthy = bool(info and info.get('healthy', False))
                        (_unhealthy_devices.discard if healthy else _unhealthy_devices.add)(idx)
                        if not healthy:
                            unhealthy.append(idx)
                    _update_compile_button()
                    if unhealthy:
                        ui.notify(f"Unhealthy device(s): {', '.join(str(i) for i in unhealthy)}",
                                  type='negative', multi_line=True, timeout=8000)
                    else:
                        ui.notify('All selected devices passed the health check', type='positive')
                finally:
                    vision_health_refresh_btn.enable()

            vision_health_refresh_btn = ui.button(
                'Re-check device health', icon='refresh', on_click=_on_refresh_vision_device_health,
            ).props('dense flat').classes('text-caption').tooltip(
                "Runs a fresh health probe on the device(s) selected above, clearing them from "
                "Compile's unhealthy list if they now pass"
            )

            await _render_detected_meta_key_field(data, widgets, 'meta_key_detected', label='Output meta key')

            ui.label('Optional:').classes('text-caption text-grey q-mt-sm')
            field('labels_file', 'labels_file (optional)', data.get('labels_file'))
            field('meta_key_override', 'meta_key_override (optional)', data.get('meta_key_override'))
            number('queue_depth', 'queue_depth (optional)', data.get('queue_depth'), format='%.0f')
            number('queue_timeout_ms', 'queue_timeout_ms (optional)', data.get('queue_timeout_ms'), format='%.0f')
        elif kind == 'vllm_vlm':
            vllm_artifacts = vllm_artifacts_result.get('artifacts', [])
            if vllm_artifacts:
                options = {a['artifact_path']: a['name'] for a in vllm_artifacts}
                cur = data.get('artifact') if data.get('artifact') in options else next(iter(options))
                widgets['artifact'] = ui.select(options, label='Artifact (from host server)', value=cur) \
                    .props('dense outlined').classes('w-full')
            else:
                field('artifact', _discovery_fallback_label(
                    'Artifact path', vllm_artifacts_result.get('reachable', False),
                    'no vLLM artifacts found under $SDK_ROOT/build/*/axscript',
                ), data.get('artifact'))
            if devices:
                name_to_index = {d['name']: d['index'] for d in devices}

                def _vllm_dev_options(health_by_name: Optional[dict] = None) -> dict:
                    """Build device dropdown options, flagging devices that failed the health check."""
                    health_by_name = health_by_name or {}
                    return {
                        d['name']: (
                            f"{d['name']} (device {d['index']})"
                            + ('' if health_by_name.get(d['name'], True) else '  ⚠ FAILED HEALTH CHECK')
                        )
                        for d in devices
                    }

                dev_options = _vllm_dev_options()
                cur_devices = [
                    dev for dev in (data.get('devices') or ([data['device']] if data.get('device') else []))
                    if dev in dev_options
                ]
                with ui.row().classes('w-full items-center no-wrap'):
                    widgets['devices'] = ui.select(
                        dev_options, label='Device(s) -- one vLLM server launches per device selected',
                        multiple=True, value=cur_devices,
                    ).props('dense outlined use-chips').classes('col')

                    async def _on_refresh_vllm_device_health() -> None:
                        """Run a health check on all listed devices, update the shared unhealthy set, and refresh the dropdown while keeping valid selections."""
                        refresh_btn.disable()
                        try:
                            indices = sorted(name_to_index.values())
                            result = await _check_devices_health_batch(indices, {})
                            if not result.get('reachable', False):
                                ui.notify('Device health check unavailable (host server unreachable)',
                                          type='warning')
                                return
                            if result.get('error') and not result.get('devices'):
                                ui.notify(f"Device health check failed: {result['error']}", type='warning')
                                return
                            by_index = {d['index']: d for d in result.get('devices', [])}
                            health_by_name = {}
                            unhealthy_names = []
                            for name, idx in name_to_index.items():
                                info = by_index.get(idx)
                                healthy = bool(info and info.get('healthy', False))
                                health_by_name[name] = healthy
                                if info is not None:
                                    (_unhealthy_devices.discard if healthy else _unhealthy_devices.add)(idx)
                                if not healthy:
                                    unhealthy_names.append(name)
                            new_options = _vllm_dev_options(health_by_name)
                            kept = [v for v in widgets['devices'].value if v in new_options]
                            widgets['devices'].set_options(new_options, value=kept)
                            if unhealthy_names:
                                ui.notify(f"Unhealthy device(s): {', '.join(unhealthy_names)}",
                                          type='negative', multi_line=True, timeout=8000)
                            else:
                                ui.notify('All listed devices passed the health check', type='positive')
                        finally:
                            refresh_btn.enable()

                    refresh_btn = ui.button(icon='refresh', on_click=_on_refresh_vllm_device_health) \
                        .props('dense flat round').tooltip('Re-check device health now')
            else:
                field('devices', _discovery_fallback_label(
                    'Device name(s), comma-separated (e.g. metis-0:23:0)', devices_result.get('reachable', False),
                    'no devices found via axdevice',
                ), ','.join(data.get('devices') or ([data['device']] if data.get('device') else [])) or None)
            number('port', 'Port (base port -- +1 per additional device)', data.get('port', 8001),
                   min=1024, max=65535, format='%.0f')
            ui.label(
                'Server-wide default -- a per-request chat_template_kwargs override '
                '(client/inference/llm_vlm.py\'s enable_thinking kwarg) still wins over this.'
            ).classes('text-caption text-grey q-mt-sm')
            widgets['enable_thinking'] = ui.switch('enable_thinking', value=data.get('enable_thinking', False))
            ui.label(
                'Fixed for the life of this server -- this backend samples the whole '
                'batch at one temperature, not per-request (a mismatched per-request '
                "override in client/inference/llm_vlm.py is silently ignored)."
            ).classes('text-caption text-grey q-mt-sm')
            number('temperature', 'temperature', data.get('temperature', 0.0), min=0, format='%.2f')

            widgets['is_vlm'] = ui.switch('Is VLM (image input)', value=bool(data.get('is_vlm', False)))
            resize_section = ui.column().classes('w-full gap-0')
            with resize_section:
                number('resize_width', 'Image resize width (px)', data.get('resize_width', 512),
                       min=1, format='%.0f')
                number('resize_height', 'Image resize height (px)', data.get('resize_height', 512),
                       min=1, format='%.0f')

            def _set_resize_visibility(visible: bool) -> None:
                """Show or hide the image resize fields (kept in layout, only visibility changes)."""
                resize_section.style(replace=f"visibility: {'visible' if visible else 'hidden'}")

            _set_resize_visibility(widgets['is_vlm'].value)
            widgets['is_vlm'].on_value_change(lambda e: _set_resize_visibility(e.value))
        elif kind == 'filter':
            with ui.row().classes('w-full items-end gap-1 no-wrap'):
                widgets['meta_key'] = ui.input(
                    'meta_key (detections key to filter, e.g. detections)',
                    value=data.get('meta_key', 'detections'),
                ).props('dense outlined').classes('flex-grow')

                async def _on_refresh_meta_key() -> None:
                    """Fill meta_key from the single upstream node of this Filter."""
                    source = _upstream_meta_key_source(node_id)
                    if source is None:
                        ui.notify('Connect this Filter to exactly one upstream node first', type='warning')
                        return
                    meta_key = await _resolve_filter_source_meta_key(source, notify=True)
                    if meta_key is None:
                        return
                    widgets['meta_key'].value = meta_key
                    ui.notify(f"meta_key set to '{meta_key}'", type='positive')

                ui.button(icon='refresh', on_click=_on_refresh_meta_key).props('dense flat round size=sm') \
                    .tooltip('Auto-detect from the connected upstream model')
            field('classes', 'classes (optional, comma-separated class indices, e.g. 0,2)',
                  data.get('classes'))
            number('min_score', 'min_score (optional)', data.get('min_score'), format='%.3f')
            number('max_score', 'max_score (optional)', data.get('max_score'), format='%.3f')
            number('min_width', 'min_width (optional)', data.get('min_width'), min=0, format='%.0f')
            number('min_height', 'min_height (optional)', data.get('min_height'), min=0, format='%.0f')
            number('top_k', 'top_k (optional)', data.get('top_k'), min=1, format='%.0f')
            widgets['which'] = ui.select(
                ['highest_score', 'center', 'all'], label='which', value=data.get('which') or 'all',
            ).props('dense outlined').classes('w-full')
        elif kind == 'sink':
            ui.label('This node type has no editable config.').classes('text-grey')
        else:
            ui.label('This node type has no editable config.').classes('text-grey')

        def _save() -> None:
            """Merge the dialog values into the node data (vision nodes also get `device_cores` and a label), update the canvas and close."""
            new_data = {**data, **_collect_widget_values(widgets)}
            if kind == 'vision':
                new_data['device_cores'] = [
                    {'device': dev, 'cores': int(w.value)} for dev, w in device_cores_widgets.items()
                ]
                new_data['label'] = f"net: {new_data.get('net_name') or _axnet_catalog_name(new_data.get('axnet') or '')}"
            flow.update_node_data(node_id, new_data)
            dialog.close()

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            if widgets:
                ui.button('Save', on_click=_save)
    dialog.open()
