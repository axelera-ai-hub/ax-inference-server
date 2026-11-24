"""Example wizards of the Pipeline Editor: dialogs that generate ready-made graphs on the canvas.

Provides the Isovision demo (one detection pipeline per group of healthy devices), the two- and three-stage cascade demos and the Iso-VLM/LLM demo, plus the pure graph builders behind them.

Note:
    Helpers owned by `app.py` are injected once through `configure()` and used as module globals.
"""


import asyncio
import copy
from typing import Optional

from nicegui import core, ui

from node_catalog import (
    CORES_PER_DEVICE, DEFAULT_IMDECODE_QUEUE_DEPTH, DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS,
    DEFAULT_IMDECODE_THREADS, DEMO_NODES, NODE_CATALOG, UNCONFIGURED_AXNET,
)
from pipeline_graph import _axnet_catalog_name

# Injected by configure().
_fetch_models = None
_fetch_devices = None
_fetch_vllm_artifacts = None
_fetch_devices_health = None
_check_devices_health_batch = None
_start_devices_health_check = None
_poll_devices_health_status = None
_fetch_cpu_topology = None
_run_devices_throughput_test = None
_fetch_devices_numa_plan = None
_build_axnet_picker = None
_render_multi_device_cores_picker = None
_text_field = None
_number_field = None
_collect_widget_values = None
_resolve_filter_source_meta_key = None
_discovery_fallback_label = None
_apply_loaded_graph = None


def configure(
    *, fetch_models, fetch_devices, fetch_vllm_artifacts, fetch_devices_health,
    check_devices_health_batch, start_devices_health_check, poll_devices_health_status, fetch_cpu_topology,
    run_devices_throughput_test, fetch_devices_numa_plan, build_axnet_picker,
    render_multi_device_cores_picker, text_field, number_field, collect_widget_values,
    resolve_filter_source_meta_key, discovery_fallback_label, apply_loaded_graph,
) -> None:
    """Inject the app-level helpers the wizards depend on (host-server fetchers, health checks, widget builders, graph loader).

    Each argument is stored in the module global of the same name with a leading underscore; they are not called here.
    """
    global _fetch_models, _fetch_devices, _fetch_vllm_artifacts, _fetch_devices_health
    global _check_devices_health_batch, _start_devices_health_check, _poll_devices_health_status, _fetch_cpu_topology
    global _run_devices_throughput_test, _fetch_devices_numa_plan, _build_axnet_picker
    global _render_multi_device_cores_picker, _text_field, _number_field, _collect_widget_values
    global _resolve_filter_source_meta_key, _discovery_fallback_label, _apply_loaded_graph
    _fetch_models = fetch_models
    _fetch_devices = fetch_devices
    _fetch_vllm_artifacts = fetch_vllm_artifacts
    _fetch_devices_health = fetch_devices_health
    _check_devices_health_batch = check_devices_health_batch
    _start_devices_health_check = start_devices_health_check
    _poll_devices_health_status = poll_devices_health_status
    _fetch_cpu_topology = fetch_cpu_topology
    _run_devices_throughput_test = run_devices_throughput_test
    _fetch_devices_numa_plan = fetch_devices_numa_plan
    _build_axnet_picker = build_axnet_picker
    _render_multi_device_cores_picker = render_multi_device_cores_picker
    _text_field = text_field
    _number_field = number_field
    _collect_widget_values = collect_widget_values
    _resolve_filter_source_meta_key = resolve_filter_source_meta_key
    _discovery_fallback_label = discovery_fallback_label
    _apply_loaded_graph = apply_loaded_graph


def _merge_cpu_ranges(cpus: list[int]) -> str:
    """Format CPU ids as a compact range string such as "0-3,8".

    Args:
        cpus (list[int]): CPU ids; duplicates and order are ignored. Adjacent ids are merged.

    Returns:
        str: Comma-separated ranges, with single CPUs written without a dash.
    """
    merged: list[list[int]] = []
    for cpu in sorted(set(cpus)):
        if merged and cpu <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], cpu)
        else:
            merged.append([cpu, cpu])
    return ','.join(f'{lo}-{hi}' if hi != lo else str(lo) for lo, hi in merged)


def _isovision_demo_graph(
    healthy_devices: list[int], per_pipeline: int, pipeline_count: int,
    numa_plan: Optional[dict[int, dict]] = None,
    bind_memory: bool = True,
    axnet: Optional[str] = None,
    imdecode_threads: Optional[int] = None,
    imdecode_queue_depth: Optional[int] = None,
    imdecode_queue_timeout_ms: Optional[int] = None,
) -> tuple[list[dict], list[dict]]:
    """Build the canvas nodes and edges for the Isovision demo: one Input -> net -> Sink row per pipeline.

    Each row copies the demo node data from `DEMO_NODES`. The first pipeline id is 'iso-detect', the following ones 'iso-detect-0', 'iso-detect-1', and so on; ports start at 50060. Devices are split into consecutive chunks of `per_pipeline`.

    Args:
        healthy_devices (list[int]): Device indices to distribute, in order.
        per_pipeline (int): Devices per pipeline.
        pipeline_count (int): Number of pipelines (rows) to create.
        numa_plan (dict[int, dict] | None, optional): Per-device plan with `cpus` and `numa_node`. When given, sets `taskset_cpus` on each Input from the chunk's CPUs.
        bind_memory (bool, optional): Also set `membind` to the NUMA node of the chunk's first planned device. Defaults to True.
        axnet (str | None, optional): Model path; defaults to the demo model.
        imdecode_threads (int | None, optional): Overrides the Input's value when not None.
        imdecode_queue_depth (int | None, optional): Overrides the Input's value when not None.
        imdecode_queue_timeout_ms (int | None, optional): Overrides the Input's value when not None.

    Returns:
        tuple[list[dict], list[dict]]: Nodes and edges.
    """

    chosen_axnet = axnet or DEMO_NODES[1]['data']['axnet']
    net_label = f'net: {_axnet_catalog_name(chosen_axnet)}'
    nodes: list[dict] = []
    edges: list[dict] = []
    for i in range(pipeline_count):
        chunk = healthy_devices[i * per_pipeline:(i + 1) * per_pipeline]
        pipeline_id = 'iso-detect' if i == 0 else f'iso-detect-{i - 1}'
        net_id = f'net-{i + 1}'
        row_y = 100 + i * 160
        input_id, sink_id = f'input-{i + 1}', f'sink-{i + 1}'
        input_data = {**copy.deepcopy(DEMO_NODES[0]['data']), 'port': 50060 + i, 'pipeline_id': pipeline_id}
        if imdecode_threads is not None:
            input_data['imdecode_threads'] = imdecode_threads
        if imdecode_queue_depth is not None:
            input_data['imdecode_queue_depth'] = imdecode_queue_depth
        if imdecode_queue_timeout_ms is not None:
            input_data['imdecode_queue_timeout_ms'] = imdecode_queue_timeout_ms
        if numa_plan is not None:
            chunk_plan = [numa_plan[d] for d in chunk if d in numa_plan]
            if chunk_plan:
                input_data['taskset_cpus'] = _merge_cpu_ranges([c for p in chunk_plan for c in p['cpus']])
                if bind_memory:
                    input_data['membind'] = chunk_plan[0]['numa_node']
        nodes.extend([
            {
                'id': input_id, 'type': 'input', 'position': {'x': 50, 'y': row_y},
                'data': input_data,
            },
            {
                'id': net_id, 'position': {'x': 250, 'y': row_y},
                'data': {
                    **copy.deepcopy(DEMO_NODES[1]['data']),
                    'axnet': chosen_axnet, 'label': net_label,
                    'devices': chunk, 'device': chunk[0], 'cores': CORES_PER_DEVICE,
                },
            },
            {
                'id': sink_id, 'type': 'output', 'position': {'x': 450, 'y': row_y},
                'data': copy.deepcopy(DEMO_NODES[2]['data']),
            },
        ])
        edges.extend([
            {'id': f'{input_id}->{net_id}', 'source': input_id, 'target': net_id},
            {'id': f'{net_id}->{sink_id}', 'source': net_id, 'target': sink_id},
        ])
    return nodes, edges


async def _on_isovision_demo_clicked() -> None:
    """Open the Isovision Demo dialog.

    The user picks a detection model and runs a device health check; the wizard then offers an optional throughput test, devices per pipeline, CPU/NUMA pinning and image-decode tuning, and "Generate Pipelines" replaces the canvas with one pipeline per group of healthy devices.
    """
    health_state = {'healthy_devices': None}
    model_data: dict = {'axnet': DEMO_NODES[1]['data']['axnet'], 'use_prebuilt_models': False}
    model_widgets: dict = {}

    loading = ui.notification('Loading model info...', spinner=True, timeout=None)
    models = await _fetch_models()
    loading.dismiss()

    with ui.dialog() as dialog, ui.card().classes('w-[28rem]'):
        ui.label('Isovision Demo').classes('text-subtitle1 font-semibold')
        ui.label(
            'Runs a device health check, then lays out one Input->Model->Sink '
            'detection pipeline per group of healthy devices, all using the '
            'model selected below.'
        ).classes('text-caption text-grey q-mb-sm')

        ui.label('Detection model:').classes('text-caption text-grey q-mt-sm')
        await _build_axnet_picker(model_data, model_widgets, models.get('vision_models', []),
                                   models.get('reachable', False))

        result_label = ui.label('Run the health check to see how many devices are healthy.').classes('text-body2')
        progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full q-mt-sm')
        progress_bar.set_visibility(False)

        async def _run_health_check() -> None:
            """Run the health check for the selected model on all devices, showing progress, and apply the result to the dialog."""
            health_btn.props('loading')
            health_btn.disable()
            generate_btn.disable()
            progress_bar.set_value(0)
            progress_bar.set_visibility(True)
            result_label.set_text('Starting device health check (real axdownloadmodel/axrunmodel '
                                   'smoke test per device -- this can take a while)...')

            chosen_axnet = model_widgets['axnet'].value or model_data.get('axnet')
            start = await _start_devices_health_check(model=chosen_axnet)
            if not start.get('reachable'):
                result = await _fetch_devices_health(model=chosen_axnet)
                progress_bar.set_visibility(False)
                health_btn.props(remove='loading')
                health_btn.enable()
                if not result.get('reachable'):
                    result_label.set_text('Health check failed -- host server unreachable (see notification).')
                    return
                await _apply_health_result(result.get('devices', []), result.get('total_count', 0))
                return

            total = max(start.get('total', 0), 1)
            while True:
                await asyncio.sleep(1.5)
                status = await _poll_devices_health_status()
                if not status.get('reachable'):
                    progress_bar.set_visibility(False)
                    health_btn.props(remove='loading')
                    health_btn.enable()
                    result_label.set_text('Health check failed -- host server unreachable (see notification).')
                    return
                completed = status.get('completed', 0)
                progress_bar.set_value(min(completed / total, 1.0))
                current_indices = sorted(status.get('current_indices', []))
                if not status.get('done'):
                    suffix = f' (currently checking device(s) {", ".join(str(i) for i in current_indices)})' \
                        if current_indices else ''
                    result_label.set_text(f'Checked {completed} / {status.get("total", total)} device(s){suffix}...')
                    continue
                health_btn.props(remove='loading')
                health_btn.enable()
                progress_bar.set_visibility(False)
                if status.get('error'):
                    result_label.set_text(f'Health check failed: {status["error"]}')
                    return
                await _apply_health_result(status.get('devices', []), status.get('total', total))
                return

        async def _apply_health_result(devices: list[dict], total: int) -> None:
            """Record the healthy device indices, summarise them, reveal the follow-up controls and show the host CPU topology."""
            healthy = [d['index'] for d in devices if d.get('healthy')]
            health_state['healthy_devices'] = healthy
            indices_text = ', '.join(str(i) for i in healthy) if healthy else 'none'
            result_label.set_text(f'{len(healthy)} / {total} device(s) healthy (indices: {indices_text})')
            devices_per_pipeline_input.set_visibility(True)
            devices_per_pipeline_input.set_value(1)
            numa_toggle.set_visibility(True)
            generate_btn.enable()
            throughput_row.set_visibility(bool(healthy))
            if not healthy:
                throughput_result_label.set_visibility(False)

            topology = await _fetch_cpu_topology()
            if topology.get('reachable'):
                if topology.get('numa_available'):
                    per_node = ', '.join(
                        f"node {n['node']}: {n['pinning_capacity']} of {n['total_cpus']} cores pinnable"
                        for n in topology['nodes']
                    )
                    cpu_topology_label.set_text(
                        f"{topology['total_cpus']} CPU cores total on this host ({per_node})"
                    )
                else:
                    cpu_topology_label.set_text(
                        f"{topology['total_cpus']} CPU cores total on this host "
                        "(single NUMA node -- CPU pinning available, no per-node memory binding)"
                    )
                cpu_topology_label.set_visibility(True)
                cores_per_device_select.set_visibility(True)
            else:
                cpu_topology_label.set_visibility(False)
                cores_per_device_select.set_visibility(False)

        health_btn = ui.button('Run Health Check', on_click=_run_health_check).classes('w-full q-mt-sm')

        async def _run_throughput_test() -> None:
            """Run the throughput test for the chosen duration on the healthy devices and show the aggregate FPS or the error."""
            healthy_devices = health_state['healthy_devices'] or []
            if not healthy_devices:
                ui.notify('Run the health check first', type='warning')
                return
            seconds = int(throughput_seconds_input.value or 0)
            if seconds < 1:
                ui.notify('Duration must be at least 1 second', type='warning')
                return
            chosen_axnet = model_widgets['axnet'].value or model_data.get('axnet')
            throughput_btn.props('loading')
            throughput_btn.disable()
            throughput_result_label.set_visibility(True)
            throughput_result_label.set_text(
                f'Running {seconds}s throughput test on device(s) '
                f'{", ".join(str(i) for i in healthy_devices)}...'
            )
            result = await _run_devices_throughput_test(healthy_devices, seconds, model=chosen_axnet)
            throughput_btn.props(remove='loading')
            throughput_btn.enable()
            if not result.get('reachable'):
                throughput_result_label.set_text(
                    'Throughput test failed -- host server unreachable (see notification).')
                return
            if result.get('error'):
                throughput_result_label.set_text(f'Throughput test failed: {result["error"]}')
                return
            failed = [d for d in result.get('devices', []) if d.get('error')]
            suffix = f' -- {len(failed)} device(s) failed' if failed else ''
            throughput_result_label.set_text(
                f'Aggregate: {result.get("aggregate_fps", 0):.1f} FPS across '
                f'{result.get("succeeded_count", 0)}/{result.get("total_count", 0)} device(s){suffix}'
            )

        with ui.row().classes('w-full items-center gap-2 q-mt-xs') as throughput_row:
            throughput_btn = ui.button('Throughput Test', on_click=_run_throughput_test) \
                .props('dense outline size=sm')
            throughput_seconds_input = ui.number('Seconds', value=30, min=1, format='%.0f') \
                .props('dense outlined').classes('w-24')
        throughput_row.set_visibility(False)
        throughput_result_label = ui.label('').classes('w-full text-caption text-grey-7 q-mb-xs')
        throughput_result_label.set_visibility(False)

        devices_per_pipeline_input = ui.number('Devices per pipeline', value=1, min=1, format='%.0f') \
            .props('dense outlined').classes('w-full q-mt-sm')
        devices_per_pipeline_input.set_visibility(False)

        numa_toggle = ui.switch('Pin CPU/NUMA (taskset + numactl)').classes('w-full q-mt-xs')
        numa_toggle.set_visibility(False)
        cpu_topology_label = ui.label('').classes('w-full text-caption text-grey-7')
        cpu_topology_label.set_visibility(False)
        cores_per_device_select = ui.select(
            {i: f'{i} core(s) per instance' for i in range(1, 8)}, value=CORES_PER_DEVICE,
        ).classes('w-full q-mt-xs')
        cores_per_device_select.set_visibility(False)

        ui.label('Server tuning (optional, applied to every generated pipeline):') \
            .classes('text-caption text-grey q-mt-sm')
        imdecode_threads_input = ui.number(
            'imdecode_threads override (blank = auto, 4x pinned cores)',
            value=DEFAULT_IMDECODE_THREADS, min=1, format='%.0f',
        ).props('dense outlined clearable').classes('w-full')
        imdecode_queue_depth_input = ui.number(
            'imdecode_queue_depth', value=DEFAULT_IMDECODE_QUEUE_DEPTH, min=1, format='%.0f',
        ).props('dense outlined').classes('w-full')
        imdecode_queue_timeout_ms_input = ui.number(
            'imdecode_queue_timeout_ms', value=DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS, min=0, format='%.0f',
        ).props('dense outlined').classes('w-full')

        async def _on_generate() -> None:
            """Validate the inputs, optionally compute a CPU/NUMA pinning plan, build the Isovision graph and load it onto the canvas.

            Only whole groups are used; leftover healthy devices are reported as unused. Warns when a pipeline spans more than one NUMA node.
            """
            healthy_devices = health_state['healthy_devices'] or []
            per_pipeline = int(devices_per_pipeline_input.value or 0)
            if not healthy_devices:
                ui.notify('Run the health check first', type='warning')
                return
            if per_pipeline < 1:
                ui.notify('Devices per pipeline must be at least 1', type='warning')
                return
            pipeline_count = len(healthy_devices) // per_pipeline
            if pipeline_count < 1:
                ui.notify(
                    f'Not enough healthy devices ({len(healthy_devices)}) for '
                    f'{per_pipeline} device(s) per pipeline', type='warning',
                )
                return

            used_devices = healthy_devices[:pipeline_count * per_pipeline]
            numa_plan_map: Optional[dict[int, dict]] = None
            bind_memory = False
            if numa_toggle.value:
                generate_btn.props('loading')
                generate_btn.disable()
                plan_result = await _fetch_devices_numa_plan(used_devices, int(cores_per_device_select.value))
                generate_btn.props(remove='loading')
                generate_btn.enable()
                if not plan_result.get('reachable'):
                    pass
                elif not plan_result.get('plan'):
                    ui.notify(
                        'Could not compute a CPU pinning plan for the selected devices (see server log)',
                        type='warning',
                    )
                else:
                    numa_plan_map = {p['index']: p for p in plan_result['plan']}
                    bind_memory = bool(plan_result.get('numa_available'))
                    if not bind_memory:
                        ui.notify(
                            'This host has no multi-NUMA topology -- pinning CPU cores only, '
                            'no NUMA memory binding applied', type='info',
                        )
                    else:
                        spanning = [
                            i for i in range(pipeline_count)
                            if len({numa_plan_map[d]['numa_node']
                                    for d in used_devices[i * per_pipeline:(i + 1) * per_pipeline]
                                    if d in numa_plan_map}) > 1
                        ]
                        if spanning:
                            ui.notify(
                                f'Pipeline(s) {", ".join(str(i) for i in spanning)} span more than one NUMA '
                                f'node -- pinned to their first device\'s node only', type='warning',
                            )

            chosen_axnet = model_widgets['axnet'].value or model_data.get('axnet')
            imdecode_threads_val = imdecode_threads_input.value
            nodes, edges = _isovision_demo_graph(
                healthy_devices, per_pipeline, pipeline_count, numa_plan_map, bind_memory=bind_memory,
                axnet=chosen_axnet,
                imdecode_threads=int(imdecode_threads_val) if imdecode_threads_val not in (None, '') else None,
                imdecode_queue_depth=int(imdecode_queue_depth_input.value or DEFAULT_IMDECODE_QUEUE_DEPTH),
                imdecode_queue_timeout_ms=int(
                    imdecode_queue_timeout_ms_input.value or DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS),
            )
            _apply_loaded_graph(nodes, edges)
            dialog.close()
            unused = len(healthy_devices) - pipeline_count * per_pipeline
            msg = f'Generated {pipeline_count} isovision pipeline(s), {per_pipeline} device(s) each'
            if unused:
                msg += f' ({unused} healthy device(s) left unused)'
            ui.notify(msg, type='positive')

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            generate_btn = ui.button('Generate Pipelines', on_click=_on_generate)
            generate_btn.disable()
    dialog.open()


def _cascade_demo_graph(
    primary: dict, filter_classes: Optional[str], roi_data: dict,
    filter_meta_key: Optional[str] = None,
    imdecode_threads: Optional[int] = None,
    imdecode_queue_depth: Optional[int] = None,
    imdecode_queue_timeout_ms: Optional[int] = None,
) -> tuple[list[dict], list[dict]]:
    """Build the nodes and edges of the cascade demo: Input -> net -> Filter -> ROI -> Sink.

    Args:
        primary (dict): Overrides for the primary Vision node data.
        filter_classes (str | None): Value for the Filter's `classes`.
        roi_data (dict): Overrides for the ROI node data.
        filter_meta_key (str | None, optional): When set, used as the Filter's `meta_key` and the ROI's `det_meta_key`.
        imdecode_threads (int | None, optional): Overrides the Input's value when not None.
        imdecode_queue_depth (int | None, optional): Overrides the Input's value when not None.
        imdecode_queue_timeout_ms (int | None, optional): Overrides the Input's value when not None.

    Returns:
        tuple[list[dict], list[dict]]: Nodes and edges.
    """

    input_data = {**copy.deepcopy(DEMO_NODES[0]['data']), 'pipeline_id': 'cascade-demo'}
    if imdecode_threads is not None:
        input_data['imdecode_threads'] = imdecode_threads
    if imdecode_queue_depth is not None:
        input_data['imdecode_queue_depth'] = imdecode_queue_depth
    if imdecode_queue_timeout_ms is not None:
        input_data['imdecode_queue_timeout_ms'] = imdecode_queue_timeout_ms

    primary_data = {
        **copy.deepcopy(NODE_CATALOG['model-vision']['data']), **primary,
        'label': f"net: {_axnet_catalog_name(primary.get('axnet') or '')}",
    }
    filter_data = {
        **copy.deepcopy(NODE_CATALOG['model-filter']['data']), 'label': 'Filter', 'classes': filter_classes,
    }
    if filter_meta_key:
        filter_data['meta_key'] = filter_meta_key
    roi_node_data = {**copy.deepcopy(NODE_CATALOG['model-roi']['data']), **roi_data, 'label': 'ROI'}
    if filter_meta_key:
        roi_node_data['det_meta_key'] = filter_meta_key

    nodes = [
        {'id': 'input-1', 'type': 'input', 'position': {'x': 50, 'y': 100}, 'data': input_data},
        {'id': 'net-1', 'position': {'x': 230, 'y': 100}, 'data': primary_data},
        {'id': 'filter-1', 'position': {'x': 410, 'y': 100}, 'data': filter_data},
        {'id': 'roi-1', 'position': {'x': 590, 'y': 100}, 'data': roi_node_data},
        {'id': 'sink-1', 'type': 'output', 'position': {'x': 790, 'y': 100}, 'data': copy.deepcopy(DEMO_NODES[2]['data'])},
    ]
    edges = [
        {'id': 'input-1->net-1', 'source': 'input-1', 'target': 'net-1'},
        {'id': 'net-1->filter-1', 'source': 'net-1', 'target': 'filter-1'},
        {'id': 'filter-1->roi-1', 'source': 'filter-1', 'target': 'roi-1'},
        {'id': 'roi-1->sink-1', 'source': 'roi-1', 'target': 'sink-1'},
    ]
    return nodes, edges


async def _on_cascade_demo_clicked(conditional: bool) -> None:
    """Open the Two-Stage or Three-Stage Conditional Cascade dialog.

    One panel per stage (primary, secondary and, if conditional, a gated tertiary model) is shown through a radio selector, plus a class filter, server tuning and a health check across all chosen models. "Generate Pipeline" builds the graph and loads it onto the canvas.

    Args:
        conditional (bool): True for the three-stage variant with a predicate gating the third model.
    """

    loading = ui.notification('Loading model info...', spinner=True, timeout=None)
    models = await _fetch_models()
    devices_result = await _fetch_devices()
    loading.dismiss()
    vision_models = models.get('vision_models', [])
    devices = devices_result['devices']

    stage_labels = ['Primary model', 'Secondary model']
    if conditional:
        stage_labels.append('Conditional tertiary model')

    stage_data: list[dict] = [
        {'axnet': UNCONFIGURED_AXNET, 'use_prebuilt_models': False, 'device': 0, 'cores': 4}
        for _ in stage_labels
    ]
    stage_widgets: list[dict] = [{} for _ in stage_labels]
    stage_device_cores_widgets: list[dict] = [{} for _ in stage_labels]

    predicate_data = {
        'name': 'roi_gate', 'type': 'meta_key_exists', 'meta_key': None,
        'indices': None, 'value': None, 'inputs_json': None, 'body': None,
    }
    predicate_widgets: dict = {}

    title = 'Three-Stage Conditional Cascade' if conditional else 'Two-Stage Cascade'
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 46rem'):
        ui.label(title).classes('text-subtitle1 font-semibold')
        flow_desc = 'Primary model -> Filter -> Secondary model'
        if conditional:
            flow_desc += ' -> (gated) Conditional tertiary model'
        ui.label(
            f'{flow_desc}, cropped per detection -- the same ROI block a hand-wired '
            'Filter->ROI chain would use.'
        ).classes('text-caption text-grey q-mb-sm')

        radio = ui.radio(stage_labels, value=stage_labels[0]).props('inline')

        stage_panels: list = []
        for i, label in enumerate(stage_labels):
            with ui.column().classes('w-full gap-0') as panel:
                ui.label(f'{label}:').classes('text-caption text-grey q-mt-sm')
                await _build_axnet_picker(stage_data[i], stage_widgets[i], vision_models,
                                           models.get('reachable', False))
                claimed: dict[int, int] = {}
                stage_device_cores_widgets[i] = _render_multi_device_cores_picker(
                    stage_data[i], stage_widgets[i], devices, devices_result, claimed)
                _text_field(stage_widgets[i], 'meta_key_override',
                            "meta_key_override (optional -- set this if this model's default "
                            'postprocess meta_key collides with another net in the same pipeline)', None)

                if conditional and i == len(stage_labels) - 1:
                    ui.label('Condition (gates this model -- same fields as ROI\'s own '
                             'Conditional mode):').classes('text-caption text-grey q-mt-sm')
                    _text_field(predicate_widgets, 'name', 'Predicate name', predicate_data['name'])
                    predicate_widgets['type'] = ui.select(
                        ['meta_key_exists', 'kpts_conf_gt', 'expr'], label='type',
                        value=predicate_data['type'],
                    ).props('dense outlined').classes('w-full')
                    predicate_fields_container = ui.column().classes('w-full gap-0')

                    def _render_predicate_fields(ptype: str) -> None:
                        """Rebuild the predicate input fields for the chosen predicate type."""
                        predicate_fields_container.clear()
                        for k in ('meta_key', 'indices', 'value', 'inputs_json', 'body'):
                            predicate_widgets.pop(k, None)
                        with predicate_fields_container:
                            if ptype == 'meta_key_exists':
                                _text_field(predicate_widgets, 'meta_key', 'predicate meta_key',
                                            predicate_data.get('meta_key'))
                            elif ptype == 'kpts_conf_gt':
                                _text_field(predicate_widgets, 'meta_key', 'predicate meta_key',
                                            predicate_data.get('meta_key'))
                                _text_field(predicate_widgets, 'indices',
                                            'indices (comma-separated, e.g. 0,1,2)', predicate_data.get('indices'))
                                _number_field(predicate_widgets, 'value', 'value (confidence threshold)',
                                              predicate_data.get('value'), format='%.3f')
                            elif ptype == 'expr':
                                _text_field(predicate_widgets, 'inputs_json',
                                            'inputs (JSON object mapping var name -> accessor expr)',
                                            predicate_data.get('inputs_json'))
                                _text_field(predicate_widgets, 'body', 'body (expression)',
                                            predicate_data.get('body'))

                    predicate_widgets['type'].on_value_change(lambda e: _render_predicate_fields(e.value))
                    _render_predicate_fields(predicate_data['type'])
            stage_panels.append(panel)

        def _on_stage_change(value: str) -> None:
            """Show only the panel of the selected stage."""
            for panel, label in zip(stage_panels, stage_labels):
                panel.set_visibility(label == value)

        _on_stage_change(stage_labels[0])
        radio.on_value_change(lambda e: _on_stage_change(e.value))

        ui.label("Filter (primary model's detections, before cropping):") \
            .classes('text-caption text-grey q-mt-sm')
        filter_classes_widget = ui.input(
            'classes (optional, comma-separated class indices to keep from the primary '
            "model's detections, e.g. 0)", value='',
        ).props('dense outlined').classes('w-full')

        ui.label('Server tuning (applied to the generated pipeline):').classes('text-caption text-grey q-mt-sm')
        imdecode_threads_input = ui.number(
            'imdecode_threads override (blank = auto, 4x pinned cores)',
            value=DEFAULT_IMDECODE_THREADS, min=1, format='%.0f',
        ).props('dense outlined clearable').classes('w-full')
        imdecode_queue_depth_input = ui.number(
            'imdecode_queue_depth', value=DEFAULT_IMDECODE_QUEUE_DEPTH, min=1, format='%.0f',
        ).props('dense outlined').classes('w-full')
        imdecode_queue_timeout_ms_input = ui.number(
            'imdecode_queue_timeout_ms', value=DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS, min=0, format='%.0f',
        ).props('dense outlined').classes('w-full')

        health_result_label = ui.label('Run the health check to verify every selected model against '
                                        'this host\'s devices.').classes('w-full text-caption text-grey-7') \
            .style('white-space: pre-line')
        health_progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full')
        health_progress_bar.set_visibility(False)

        async def _run_one_model_health_check(axnet: str) -> Optional[dict]:
            """Run the device health check for one model and wait for it to finish.

            Returns:
                dict | None: `{'healthy': [indices], 'total': int}`, or None if the host server is unreachable or reports an error.
            """
            start = await _start_devices_health_check(model=axnet)
            if not start.get('reachable'):
                result = await _fetch_devices_health(model=axnet)
                if not result.get('reachable'):
                    return None
                return {'healthy': [d['index'] for d in result.get('devices', []) if d.get('healthy')],
                        'total': result.get('total_count', 0)}
            total = max(start.get('total', 0), 1)
            while True:
                await asyncio.sleep(1.5)
                status = await _poll_devices_health_status()
                if not status.get('reachable'):
                    return None
                health_progress_bar.set_value(min(status.get('completed', 0) / total, 1.0))
                if not status.get('done'):
                    continue
                if status.get('error'):
                    return None
                return {'healthy': [d['index'] for d in status.get('devices', []) if d.get('healthy')],
                        'total': status.get('total', total)}

        async def _run_health_check() -> None:
            """Run the health check for each stage's selected model in turn and list the results in the dialog."""
            health_btn.props('loading')
            health_btn.disable()
            health_progress_bar.set_value(0)
            health_progress_bar.set_visibility(True)
            lines = []
            for label, widgets in zip(stage_labels, stage_widgets):
                axnet_widget = widgets.get('axnet')
                axnet = axnet_widget.value if axnet_widget is not None else None
                if not axnet:
                    lines.append(f'{label}: no model selected yet -- skipped')
                    health_result_label.set_text('\n'.join(lines))
                    continue
                health_result_label.set_text('\n'.join(lines + [f'Checking {label}...']))
                result = await _run_one_model_health_check(axnet)
                if result is None:
                    lines.append(f'{label}: health check failed -- host server unreachable (see notification)')
                else:
                    healthy, total = result['healthy'], result['total']
                    indices_text = ', '.join(str(i) for i in healthy) if healthy else 'none'
                    lines.append(f'{label}: {len(healthy)}/{total} device(s) healthy (indices: {indices_text})')
                health_result_label.set_text('\n'.join(lines))
            health_progress_bar.set_visibility(False)
            health_btn.props(remove='loading')
            health_btn.enable()

        health_btn = ui.button('Run Health Check (all models)', on_click=_run_health_check).classes('w-full q-mt-sm')

        async def _on_generate() -> None:
            """Validate the stage choices, build the cascade graph and load it onto the canvas.

            Refuses stages without a model or device, and devices whose cores claimed across stages exceed `CORES_PER_DEVICE`.
            """
            per_stage_device_cores: list[list[dict]] = []
            for i, label in enumerate(stage_labels):
                axnet_widget = stage_widgets[i].get('axnet')
                axnet = axnet_widget.value if axnet_widget is not None else None
                if not axnet:
                    ui.notify(f'Pick a model for {label} first', type='warning')
                    return
                dc_widgets = stage_device_cores_widgets[i]
                if not dc_widgets:
                    ui.notify(f'Select at least one device for {label}', type='warning')
                    return
                per_stage_device_cores.append(
                    [{'device': dev, 'cores': int(w.value)} for dev, w in dc_widgets.items()]
                )

            combined: dict[int, int] = {}
            overcommitted: set = set()
            for device_cores in per_stage_device_cores:
                for dc in device_cores:
                    dev, cores = int(dc['device']), int(dc['cores'])
                    combined[dev] = combined.get(dev, 0) + cores
                    if combined[dev] > CORES_PER_DEVICE:
                        overcommitted.add(dev)
            if overcommitted:
                ui.notify(
                    f'Device(s) {", ".join(str(d) for d in sorted(overcommitted))} would have more than '
                    f'{CORES_PER_DEVICE} cores claimed across stages -- reduce cores or pick different devices',
                    type='warning', multi_line=True,
                )
                return

            def _stage_payload(i: int) -> dict:
                """Collect the model, device and core settings of one stage into node data."""
                return {
                    'axnet': stage_widgets[i]['axnet'].value,
                    'device': per_stage_device_cores[i][0]['device'],
                    'cores': per_stage_device_cores[i][0]['cores'],
                    'device_cores': per_stage_device_cores[i],
                    'meta_key_override': stage_widgets[i]['meta_key_override'].value or None,
                }

            roi_catalog_defaults = NODE_CATALOG['model-roi']['data']
            roi_data: dict = {
                'mode': 'conditional' if conditional else 'simple',
                'model_a': {**copy.deepcopy(roi_catalog_defaults['model_a']), **_stage_payload(1)},
            }
            if conditional:
                roi_data['model_b'] = {**copy.deepcopy(roi_catalog_defaults['model_b']), **_stage_payload(2)}
                roi_data['predicate'] = {**predicate_data, **_collect_widget_values(predicate_widgets)}

            primary_payload = _stage_payload(0)
            filter_meta_key = await _resolve_filter_source_meta_key(('vision', primary_payload), notify=True)

            imdecode_threads_val = imdecode_threads_input.value
            nodes, edges = _cascade_demo_graph(
                primary_payload, filter_classes_widget.value or None, roi_data,
                filter_meta_key=filter_meta_key,
                imdecode_threads=int(imdecode_threads_val) if imdecode_threads_val not in (None, '') else None,
                imdecode_queue_depth=int(imdecode_queue_depth_input.value or DEFAULT_IMDECODE_QUEUE_DEPTH),
                imdecode_queue_timeout_ms=int(
                    imdecode_queue_timeout_ms_input.value or DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS),
            )
            _apply_loaded_graph(nodes, edges)
            dialog.close()
            ui.notify(f'Generated {title.lower()} pipeline', type='positive')

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Generate Pipeline', on_click=_on_generate)
    dialog.open()


# Appended to device names that failed the health check in the Iso-VLM/LLM dropdowns.
_FAILED_HEALTH_SUFFIX = '  ⚠ FAILED HEALTH CHECK'


def _iso_vllm_demo_graph(pipeline_configs: list[dict], base_port: int) -> tuple[list[dict], list[dict]]:
    """Build the nodes and edges of the Iso-VLM/LLM demo: one Input -> (V/L)LM -> Sink row per configuration.

    Args:
        pipeline_configs (list[dict]): Per-pipeline overrides for the (V/L)LM node data.
        base_port (int): Port of the first pipeline; pipeline i uses `base_port + i`.

    Returns:
        tuple[list[dict], list[dict]]: Nodes and edges.
    """

    vllm_defaults = NODE_CATALOG['model-vllm-vlm']['data']
    nodes: list[dict] = []
    edges: list[dict] = []
    for i, cfg in enumerate(pipeline_configs):
        row_y = 100 + i * 160
        input_id, vllm_id, sink_id = f'input-{i + 1}', f'vllm-{i + 1}', f'sink-{i + 1}'
        vllm_data = {**copy.deepcopy(vllm_defaults), **cfg, 'port': base_port + i, 'label': '(V/L)LM'}
        nodes.extend([
            {
                'id': input_id, 'type': 'input', 'position': {'x': 50, 'y': row_y},
                'data': {'label': NODE_CATALOG['source-input']['label'],
                          **copy.deepcopy(NODE_CATALOG['source-input']['data'])},
            },
            {'id': vllm_id, 'position': {'x': 250, 'y': row_y}, 'data': vllm_data},
            {
                'id': sink_id, 'type': 'output', 'position': {'x': 450, 'y': row_y},
                'data': {'label': NODE_CATALOG['sink-output']['label'],
                          **copy.deepcopy(NODE_CATALOG['sink-output']['data'])},
            },
        ])
        edges.extend([
            {'id': f'{input_id}->{vllm_id}', 'source': input_id, 'target': vllm_id},
            {'id': f'{vllm_id}->{sink_id}', 'source': vllm_id, 'target': sink_id},
        ])
    return nodes, edges


async def _on_iso_vllm_demo_clicked() -> None:
    """Open the Iso-VLM/LLM-Demo wizard.

    Steps: choose the number of pipelines (with a device health check), configure each pipeline (model artifact, device, thinking, temperature, VLM and image size), then choose the base port and save, which loads the graph onto the canvas.
    """

    loading = ui.notification('Loading model & device info...', spinner=True, timeout=None)
    vllm_artifacts_result = await _fetch_vllm_artifacts()
    devices_result = await _fetch_devices()
    loading.dismiss()

    vllm_artifacts = vllm_artifacts_result.get('artifacts', [])
    devices = devices_result.get('devices', [])
    vllm_defaults = NODE_CATALOG['model-vllm-vlm']['data']

    state = {'step': 0, 'count': 1, 'health_by_name': None}
    pipeline_configs: list[dict] = []
    active_widgets: dict = {}

    def _artifact_options() -> dict:
        """Return the dropdown options mapping artifact path to display name."""
        return {a['artifact_path']: a['name'] for a in vllm_artifacts}

    def _is_healthy(name: str) -> bool:
        """Return True if the device passed the health check or no check has run yet."""
        health_by_name = state['health_by_name']
        return True if health_by_name is None else health_by_name.get(name, True)

    def _device_options() -> dict:
        """Return the device dropdown options, flagging devices that failed the health check."""
        return {
            d['name']: f"{d['name']} (device {d['index']})" + ('' if _is_healthy(d['name']) else _FAILED_HEALTH_SUFFIX)
            for d in devices
        }

    def _health_summary_text() -> str:
        """Return the health summary line, or a prompt to run the check first."""
        health_by_name = state['health_by_name']
        if health_by_name is None:
            return 'Run the device health check first -- devices that fail it are flagged in each pipeline\'s device list.'
        healthy = [d['index'] for d in devices if health_by_name.get(d['name'], False)]
        indices_text = ', '.join(str(i) for i in healthy) if healthy else 'none'
        return f'{len(healthy)}/{len(devices)} device(s) healthy (indices: {indices_text})'

    with ui.dialog() as dialog, ui.card().classes('w-[30rem]'):
        ui.label('Iso-VLM/LLM-Demo').classes('text-subtitle1 font-semibold')
        ui.label(
            'Deploy several independent (V/L)LM pipelines at once -- each gets '
            'its own Input->(V/L)LM->Sink chain on the canvas, its own model, '
            'device, and settings, and its own port.'
        ).classes('text-caption text-grey q-mb-sm')
        step_container = ui.column().classes('w-full gap-2')
        button_row = ui.row().classes('w-full justify-end q-mt-md')

        def _render_count_step() -> None:
            """Show step 1: the pipeline count input and the device health check."""
            step_container.clear()
            button_row.clear()
            with step_container:
                count_input = ui.number(
                    'How many parallel pipelines do you want to deploy?',
                    value=state['count'], min=1, format='%.0f',
                ).props('dense outlined lang=en-US').classes('w-full')

                health_result_label = ui.label(_health_summary_text()).classes('w-full text-caption text-grey-7')

                async def _run_device_health_check() -> None:
                    """Check the health of all listed devices, update the per-device flags and the shared unhealthy-device set, and notify the result."""
                    health_btn.props('loading')
                    health_btn.disable()
                    try:
                        indices = sorted(d['index'] for d in devices)
                        result = await _check_devices_health_batch(indices, {})
                        if not result.get('reachable', False):
                            ui.notify('Device health check unavailable (host server unreachable)', type='warning')
                            return
                        if result.get('error') and not result.get('devices'):
                            ui.notify(f"Device health check failed: {result['error']}", type='warning')
                            return
                        by_index = {d['index']: d for d in result.get('devices', [])}
                        health_by_name = {}
                        unhealthy_names = []
                        for d in devices:
                            info = by_index.get(d['index'])
                            healthy = bool(info and info.get('healthy', False))
                            health_by_name[d['name']] = healthy
                            if info is not None:
                                unhealthy = core.app.state.unhealthy_devices
                                (unhealthy.discard if healthy else unhealthy.add)(d['index'])
                            if not healthy:
                                unhealthy_names.append(d['name'])
                        state['health_by_name'] = health_by_name
                        health_result_label.set_text(_health_summary_text())
                        if unhealthy_names:
                            ui.notify(f"Unhealthy device(s): {', '.join(unhealthy_names)}",
                                      type='negative', multi_line=True, timeout=8000)
                        else:
                            ui.notify('All listed devices passed the health check', type='positive')
                    finally:
                        health_btn.props(remove='loading')
                        health_btn.enable()

                health_btn = ui.button(
                    'Re-check device health', icon='refresh', on_click=_run_device_health_check,
                ).props('dense outline').classes('w-full').tooltip('Re-check device health now')

            def _on_next() -> None:
                """Validate the count (and that a health check has run), size the config list and move to the first pipeline step."""
                count = int(count_input.value or 0)
                if count < 1:
                    ui.notify('Enter at least 1 pipeline', type='warning')
                    return
                if devices and state['health_by_name'] is None:
                    ui.notify('Run the device health check first', type='warning')
                    return
                state['count'] = count
                while len(pipeline_configs) < count:
                    pipeline_configs.append(copy.deepcopy(vllm_defaults))
                del pipeline_configs[count:]
                state['step'] = 1
                _render_pipeline_step()

            with button_row:
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Next', on_click=_on_next)

        def _save_active_widgets_into(index: int) -> None:
            """Copy the values of the currently shown pipeline widgets into the config at `index`."""
            if not active_widgets:
                return
            cfg = pipeline_configs[index]
            cfg['artifact'] = active_widgets['artifact'].value
            device_value = active_widgets['devices'].value
            if isinstance(device_value, str):
                cfg['devices'] = [device_value] if device_value.strip() else []
            else:
                cfg['devices'] = list(device_value or [])
            cfg['enable_thinking'] = bool(active_widgets['enable_thinking'].value)
            cfg['temperature'] = float(active_widgets['temperature'].value or 0.0)
            cfg['is_vlm'] = bool(active_widgets['is_vlm'].value)
            cfg['resize_width'] = int(active_widgets['resize_width'].value or 512)
            cfg['resize_height'] = int(active_widgets['resize_height'].value or 512)

        def _render_pipeline_step() -> None:
            """Show the configuration form for the current pipeline, prefilled from its stored config."""
            index = state['step'] - 1
            cfg = pipeline_configs[index]
            active_widgets.clear()
            step_container.clear()
            button_row.clear()
            with step_container:
                ui.label(f'Pipeline {index + 1} of {state["count"]}').classes('text-body1 font-medium')

                artifact_options = _artifact_options()
                if artifact_options:
                    cur = cfg.get('artifact') if cfg.get('artifact') in artifact_options \
                        else next(iter(artifact_options))
                    active_widgets['artifact'] = ui.select(
                        artifact_options, label='Model', value=cur,
                    ).props('dense outlined').classes('w-full')
                else:
                    active_widgets['artifact'] = ui.input(
                        _discovery_fallback_label(
                            'Artifact path', vllm_artifacts_result.get('reachable', False),
                            'no vLLM artifacts found under $SDK_ROOT/build/*/axscript',
                        ), value=cfg.get('artifact') or '',
                    ).props('dense outlined').classes('w-full')

                device_options = _device_options()
                cur_devices = cfg.get('devices') or []
                cur_device = cur_devices[0] if cur_devices else None
                if device_options:
                    if cur_device not in device_options:
                        cur_device = next(
                            (name for name in device_options if _is_healthy(name)), next(iter(device_options)),
                        )
                    active_widgets['devices'] = ui.select(
                        device_options, label='Device', value=cur_device,
                    ).props('dense outlined').classes('w-full')
                else:
                    active_widgets['devices'] = ui.input(
                        _discovery_fallback_label(
                            'Device name (e.g. metis-0:23:0)', devices_result.get('reachable', False),
                            'no devices found via axdevice',
                        ), value=cur_device or '',
                    ).props('dense outlined').classes('w-full')

                active_widgets['enable_thinking'] = ui.switch(
                    'enable_thinking', value=bool(cfg.get('enable_thinking', False)),
                )
                active_widgets['temperature'] = ui.number(
                    'temperature', value=cfg.get('temperature', 0.0), min=0, format='%.2f',
                ).props('dense outlined lang=en-US').classes('w-full')

                active_widgets['is_vlm'] = ui.switch(
                    'Is VLM (image input)', value=bool(cfg.get('is_vlm', False)),
                )
                resize_section = ui.column().classes('w-full gap-0')
                with resize_section:
                    active_widgets['resize_width'] = ui.number(
                        'Image resize width (px)', value=cfg.get('resize_width', 512), min=1, format='%.0f',
                    ).props('dense outlined lang=en-US').classes('w-full')
                    active_widgets['resize_height'] = ui.number(
                        'Image resize height (px)', value=cfg.get('resize_height', 512), min=1, format='%.0f',
                    ).props('dense outlined lang=en-US').classes('w-full')

                def _set_resize_visibility(visible: bool) -> None:
                    """Show or hide the image resize fields (kept in layout, only visibility changes)."""
                    resize_section.style(replace=f"visibility: {'visible' if visible else 'hidden'}")

                _set_resize_visibility(active_widgets['is_vlm'].value)
                active_widgets['is_vlm'].on_value_change(lambda e: _set_resize_visibility(e.value))

            def _on_back() -> None:
                """Save the current form and go back one step."""
                _save_active_widgets_into(index)
                state['step'] -= 1
                _render_count_step() if state['step'] == 0 else _render_pipeline_step()

            def _on_next() -> None:
                """Validate the model and device, save the form and move to the next pipeline or the final step."""
                artifact_value = active_widgets['artifact'].value
                if not (artifact_value or '').strip():
                    ui.notify('Pick a model for this pipeline', type='warning')
                    return
                device_value = active_widgets['devices'].value
                has_device = bool(device_value) if not isinstance(device_value, str) else bool(device_value.strip())
                if not has_device:
                    ui.notify('Pick a device for this pipeline', type='warning')
                    return
                if isinstance(device_value, str) and device_value in device_options and not _is_healthy(device_value):
                    ui.notify(f'{device_value} failed its health check -- pick a healthy device if you can',
                              type='warning')
                _save_active_widgets_into(index)
                state['step'] += 1
                _render_pipeline_step() if index + 1 < state['count'] else _render_final_step()

            with button_row:
                ui.button('Back', on_click=_on_back).props('flat')
                ui.button('Next', on_click=_on_next)

        def _render_final_step() -> None:
            """Show the last step: the base port input."""
            step_container.clear()
            button_row.clear()
            with step_container:
                ui.label(f'{state["count"]} pipeline(s) configured.').classes('text-body1 font-medium')
                base_port_input = ui.number(
                    'Base port (each pipeline gets base_port + its index)',
                    value=8001, min=1024, max=65535, format='%.0f',
                ).props('dense outlined lang=en-US').classes('w-full')

            def _on_back() -> None:
                """Go back to the last pipeline step."""
                state['step'] -= 1
                _render_pipeline_step()

            def _on_save() -> None:
                """Validate the port range, build the graph and load it onto the canvas."""
                base_port = int(base_port_input.value or 0)
                if base_port < 1024 or base_port + state['count'] - 1 > 65535:
                    ui.notify('Base port out of range for this many pipelines', type='warning')
                    return
                nodes, edges = _iso_vllm_demo_graph(pipeline_configs, base_port)
                _apply_loaded_graph(nodes, edges)
                dialog.close()
                ui.notify(f'Generated {state["count"]} (V/L)LM pipeline(s)', type='positive')

            with button_row:
                ui.button('Back', on_click=_on_back).props('flat')
                ui.button('Save', on_click=_on_save)

        _render_count_step()
    dialog.open()
