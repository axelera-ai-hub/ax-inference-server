#!/usr/bin/env python3
"""No-Code Pipeline Editor GUI: the NiceGUI entry point (run with `python3 app.py`).

Builds the Pipeline Editor canvas, the Benchmarking tab and their drawers, wires them to the helper modules (pipeline_graph, pipeline_compile, node_dialogs, example_wizards, chat, benchmark, agent_surface), and starts the web server.

Note:
    Environment: HOST_SERVER_URL / HOST_SERVER_API_KEY locate host_server.py (SDK_ROOT is fetched from it when unset); GUI_APP_HOST (default 0.0.0.0) and GUI_APP_PORT (default 8080) set the listen address. State shared across page loads lives on core.app.state and is created only when absent.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
import psutil
import yaml
from components.pipeline_flow import PipelineFlow
from pydantic import ValidationError

from nicegui import app, core, ui

# Make the shared configs/utils, compiler and client packages importable by bare module name.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'configs' / 'utils'))

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'compiler'))

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

GENERATED_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), 'generated_configs')
COMPILED_SPECS_DIR = os.path.join(os.path.dirname(__file__), 'compiled_specs')
PROMPT_LIBRARY_PATH = os.path.join(GENERATED_CONFIGS_DIR, 'prompt_library.jsonl')
PROMPT_LIBRARY_IMAGES_DIR = os.path.join(GENERATED_CONFIGS_DIR, 'prompt_library_images')

def _reap_orphaned_benchmark_workers() -> None:
    """Kill benchmark worker processes left over from a previous GUI instance.

    A candidate is a process that is not this one, has been re-parented to init (ppid 1), runs the same Python executable and was started through multiprocessing's spawn_main. Processes that vanish or deny access during the scan are skipped. Prints a startup line when anything was killed.
    """

    own_pid = os.getpid()
    own_exe = sys.executable
    reaped = []
    for proc in psutil.process_iter(['pid', 'ppid', 'exe', 'cmdline']):
        try:
            info = proc.info
            if info['pid'] == own_pid or info['ppid'] != 1 or info['exe'] != own_exe:
                continue
            cmdline = info['cmdline'] or []
            if not any('multiprocessing.spawn' in part and 'spawn_main' in part for part in cmdline):
                continue
            proc.kill()
            reaped.append(info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if reaped:
        print(f'[startup] reaped {len(reaped)} orphaned benchmark worker process(es) '
              f'from a previous GUI instance: {reaped}', flush=True)


# Orphans can only exist from an earlier process, so reap only when the state is first created.
if not hasattr(core.app.state, 'benchmark_sources'):
    core.app.state.benchmark_sources = {}
    _reap_orphaned_benchmark_workers()
BENCHMARK_SOURCES: dict = core.app.state.benchmark_sources

HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')

# Ask host_server.py for its SDK root unless SDK_ROOT is already set.
if HOST_SERVER_URL and not os.environ.get('SDK_ROOT'):
    try:
        _resp = httpx.get(
            f'{HOST_SERVER_URL}/api/v1/sdk-root', headers={'X-API-Key': HOST_SERVER_API_KEY}, timeout=5.0,
        )
        _resp.raise_for_status()
        _discovered_sdk_root = _resp.json()['sdk_root']
        os.environ['SDK_ROOT'] = _discovered_sdk_root
        os.environ.setdefault('AXELERA_FRAMEWORK', _discovered_sdk_root)
        print(f'[app.py] SDK_ROOT discovered from host_server.py: {_discovered_sdk_root}', flush=True)
    except Exception as _exc:
        print(f'[app.py] could not discover SDK_ROOT from host_server.py ({_exc}) -- '
              'Generate Config YAML / Compile Pipeline will fail with "sdk_root must be a '
              'non-empty string" until SDK_ROOT is set, either by hand or by host_server.py '
              'being reachable at startup', flush=True)

from node_catalog import DEMO_EDGES, DEMO_NODES, NODE_CATALOG, PALETTE_TREE

if not hasattr(core.app.state, 'global_settings'):
    core.app.state.global_settings = {
        'use_axinference_net_opencl': True,
        'use_simd_decode': True,
        'restart_interval': 0,
        'pipeline_depth': None,
    }
GLOBAL_SETTINGS: dict = core.app.state.global_settings

if not hasattr(core.app.state, 'current_graph'):
    core.app.state.current_graph = {'nodes': DEMO_NODES, 'edges': DEMO_EDGES}
current_graph: dict = core.app.state.current_graph

import pipeline_graph
from pipeline_graph import (
    _axnet_catalog_name, _build_yaml, _connected_vllm_nodes, _graph_from_vision_config,
    _graph_signature, _node_by_id, _node_device_indices,
    _resolve_all_pipelines, _save_yaml, _upstream_meta_key_source,
)

import example_wizards
from example_wizards import (
    _on_cascade_demo_clicked, _on_isovision_demo_clicked, _on_iso_vllm_demo_clicked,
)

import chat
from chat import (
    CHAT_MAX_IMAGES, CHAT_TOKEN_DEBOUNCE_S, _PLAY_BTN_IDLE_PROPS,
    _chat_activate_session, _chat_refresh_groups, _chat_token_budget_tick,
    _on_chat_add_image_clicked, _on_chat_clear_clicked, _on_chat_send_clicked,
    _on_chat_text_changed, _on_prompt_library_open_clicked, _on_prompt_library_play_clicked,
)

import benchmark
from benchmark import (
    BENCHMARK_DRAIN_INTERVAL_S, BENCHMARK_METRICS_SAMPLE_INTERVAL_S,
    MONITOR_METRICS_SAMPLE_INTERVAL_S, _BENCHMARK_STREAM_SETTINGS, _MONITOR_CHECKBOXES,
    _benchmark_aggregate_fps_ema_alpha, _benchmark_aggregate_fps_filter_mode,
    _benchmark_aggregate_fps_hampel_nsigmas, _benchmark_aggregate_fps_hampel_window,
    _benchmark_combined_plot_layout, _benchmark_drain_tick, _benchmark_endpoints,
    _benchmark_metrics_history_maxlen, _benchmark_metrics_tick,
    _benchmark_pipeline_ids, _benchmark_ring_buffer_names, _benchmark_show_aggregate_error,
    _benchmark_show_aggregate_fps, _benchmark_show_cpu_percent,
    _benchmark_show_cpu_percent_percore, _benchmark_show_mem_percent,
    _benchmark_show_monitor_aggregate_core, _benchmark_show_monitor_aggregate_ddr,
    _benchmark_show_monitor_aggregate_mvm, _benchmark_show_monitor_aggregate_syscore,
    _benchmark_show_monitor_per_device_raw, _benchmark_show_monitor_power_sensor_0,
    _benchmark_show_monitor_power_sensor_1, _benchmark_show_per_source_error,
    _benchmark_show_per_source_fps, _benchmark_show_per_source_latency,
    _benchmark_stream_playback_delay_s, _benchmark_thumbnail_refresh_interval_s,
    _monitor_stats_tick, _on_benchmark_add_file_clicked, _on_benchmark_add_webcam_clicked,
    _on_benchmark_aggregate_fps_ema_alpha_changed,
    _on_benchmark_aggregate_fps_filter_mode_changed, _on_benchmark_aimd_backoff_changed,
    _on_benchmark_backpressure_changed, _on_benchmark_clear_plot_clicked,
    _on_benchmark_endpoints_changed, _on_benchmark_hampel_nsigmas_changed,
    _on_benchmark_hampel_window_changed, _on_benchmark_history_maxlen_changed,
    _on_benchmark_pipeline_ids_changed, _on_benchmark_playback_delay_changed,
    _on_benchmark_remove_all_clicked, _on_benchmark_request_timeout_changed,
    _on_benchmark_show_aggregate_error_changed, _on_benchmark_show_aggregate_fps_changed,
    _on_benchmark_show_cpu_percent_changed, _on_benchmark_show_cpu_percent_percore_changed,
    _on_benchmark_show_mem_percent_changed, _on_benchmark_show_monitor_aggregate_core_changed,
    _on_benchmark_show_monitor_aggregate_ddr_changed,
    _on_benchmark_show_monitor_aggregate_mvm_changed,
    _on_benchmark_show_monitor_aggregate_syscore_changed,
    _on_benchmark_show_monitor_per_device_raw_changed,
    _on_benchmark_show_monitor_power_sensor_0_changed,
    _on_benchmark_show_monitor_power_sensor_1_changed, _on_monitor_set_power_clicked,
    MONITOR_POWER_LIMIT_MAX_W,
    _on_benchmark_show_per_source_error_changed, _on_benchmark_show_per_source_fps_changed,
    _on_benchmark_show_per_source_latency_changed, _on_benchmark_stream_format_changed,
    _on_benchmark_stream_fps_changed, _on_benchmark_stream_max_width_changed,
    _on_benchmark_stream_quality_changed, _on_benchmark_stream_resolution_changed,
    _on_benchmark_thumbnail_interval_changed, _read_file_bytes, _rehydrate_benchmark_sources,
    _update_monitor_checkbox_availability,
)

import node_dialogs
from node_dialogs import (
    _build_axnet_picker, _collect_widget_values, _discovery_fallback_label, _number_field,
    _on_node_dblclick, _render_multi_device_cores_picker, _text_field,
)
import pipeline_compile
from pipeline_compile import (
    _check_devices_health_batch, _cleanup_all_pipelines, _download_prebuilt_model, _fetch_cpu_topology,
    _fetch_devices, _fetch_devices_health, _fetch_devices_numa_plan, _fetch_model_meta_key, _fetch_models,
    _fetch_prebuilt_models, _fetch_vllm_artifacts, _on_compile_clicked, _poll_devices_health_status,
    _render_detected_meta_key_field, _run_devices_throughput_test, _start_devices_health_check,
)

if not hasattr(core.app.state, 'node_counter'):
    core.app.state.node_counter = 0

if not hasattr(core.app.state, 'last_generated'):
    core.app.state.last_generated = {'doc_id': None, 'kind': None, 'yaml_text': None, 'out_path': None}
_last_generated: dict = core.app.state.last_generated

if not hasattr(core.app.state, 'unhealthy_devices'):
    core.app.state.unhealthy_devices = set()
_unhealthy_devices: set[int] = core.app.state.unhealthy_devices

if not hasattr(core.app.state, 'compile_in_progress'):
    core.app.state.compile_in_progress = False


DEBUG_RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), 'debug_recordings')
_recorded_steps: list = []


async def _on_graph_changed(event) -> None:
    """Handle a graph edit coming from the PipelineFlow canvas.

    Stores the new nodes and edges in current_graph and on the sender, refreshes the Generate and Compile buttons, and, when the graph signature actually changed, discards the last generated config and auto-fills meta keys for newly added edges.

    Args:
        event: Canvas event whose args hold 'nodes' and 'edges' and whose sender is the PipelineFlow.
    """
    nodes = event.args.get('nodes', [])
    edges = event.args.get('edges', [])
    old_edges = current_graph['edges']
    changed = _graph_signature(nodes, edges) != _graph_signature(current_graph['nodes'], old_edges)
    current_graph['nodes'] = nodes
    current_graph['edges'] = edges
    event.sender.agent_nodes = nodes
    event.sender.agent_edges = edges
    _update_generate_button()
    if changed:
        _last_generated.update(doc_id=None, kind=None, yaml_text=None, out_path=None)
    _update_compile_button()
    if changed:
        await _auto_populate_filter_meta_keys(old_edges, edges)


# Node kind -> data field that holds the meta key it consumes.
_META_KEY_FIELD_BY_TARGET_KIND = {'filter': 'meta_key', 'roi': 'det_meta_key'}


async def _auto_populate_filter_meta_keys(old_edges: list[dict], new_edges: list[dict]) -> None:
    """Fill the meta-key field of filter and ROI nodes that just received an incoming edge.

    For each edge present in new_edges but not in old_edges, resolves the upstream node's meta key and writes it into the target node (meta_key for a filter, det_meta_key for an ROI). Skips edges whose target or upstream source cannot be resolved, and values already set.

    Args:
        old_edges (list[dict]): Canvas edges before the change.
        new_edges (list[dict]): Canvas edges after the change.
    """
    old_ids = {e.get('id') for e in old_edges}
    added = [e for e in new_edges if e.get('id') not in old_ids]
    for edge in added:
        target_id = edge.get('target')
        target = _node_by_id(target_id)
        if target is None:
            continue
        target_kind = target.get('data', {}).get('kind')
        field = _META_KEY_FIELD_BY_TARGET_KIND.get(target_kind)
        if field is None:
            continue
        source = _upstream_meta_key_source(target_id)
        if source is None:
            continue
        meta_key = await _resolve_filter_source_meta_key(source, notify=False)
        if not meta_key or meta_key == target['data'].get(field):
            continue
        flow.update_node_data(target_id, {**target['data'], field: meta_key})


def _on_debug_event(event) -> None:
    """Append a step recorded by the canvas to the in-memory debug recording."""
    _recorded_steps.append(event.args)


def _on_toggle_recording(event) -> None:
    """Start or stop the browser debug recording from the Debug switch.

    Turning it on clears the recorded steps and enables recording on the canvas. Turning it off disables recording and writes the steps to DEBUG_RECORDINGS_DIR/session_<unix time>.json.

    Args:
        event: Switch change event; event.value is the new state.
    """
    global _recorded_steps
    if event.value:
        _recorded_steps = []
        flow.set_recording(True)
        ui.notify('Debug started', type='warning')
    else:
        flow.set_recording(False)
        os.makedirs(DEBUG_RECORDINGS_DIR, exist_ok=True)
        path = os.path.join(DEBUG_RECORDINGS_DIR, f'session_{int(time.time())}.json')
        with open(path, 'w') as f:
            json.dump(_recorded_steps, f, indent=2)
        ui.notify(f'Saved {len(_recorded_steps)} steps to {path}', type='positive')


async def _resolve_filter_source_meta_key(source: tuple[str, dict], *, notify: bool) -> str | None:
    """Determine the meta key produced by the node feeding a filter or ROI node.

    An ROI source uses the meta_key_override or cls_meta_key of its model_b (when mode is 'conditional') or model_a. A vision source uses its meta_key_override, else the key fetched for its selected AxNet model. Any other source kind is unsupported.

    Args:
        source (tuple[str, dict]): The upstream node's (kind, data), as returned by _upstream_meta_key_source.
        notify (bool): Show a warning toast explaining why no key could be found.

    Returns:
        str | None: The meta key, or None when it cannot be determined.
    """
    src_kind, src_data = source
    if src_kind == 'roi':
        sub_model = src_data.get('model_b') if src_data.get('mode') == 'conditional' else src_data.get('model_a')
        meta_key = (sub_model or {}).get('meta_key_override') or (sub_model or {}).get('cls_meta_key')
        if not meta_key:
            if notify:
                ui.notify('Upstream ROI node has no meta_key configured yet', type='warning')
            return None
        return meta_key
    if src_kind == 'vision':
        override = src_data.get('meta_key_override')
        if override:
            return override
        model_name = _axnet_catalog_name(src_data.get('axnet') or '')
        if not model_name:
            if notify:
                ui.notify('Upstream Vision node has no model selected yet', type='warning')
            return None
        return await _fetch_model_meta_key(model_name)
    if notify:
        ui.notify(f"Upstream node is a '{src_kind}' node -- can't auto-detect a meta_key from it", type='warning')
    return None


def _generate_disabled_reason() -> str | None:
    """Explain why the current graph cannot produce a config.

    Returns:
        str | None: The validation error from _resolve_all_pipelines, or None when generation is possible.
    """
    try:
        _resolve_all_pipelines()
    except ValueError as exc:
        return str(exc)
    return None


def _update_generate_button() -> None:
    """Enable or disable the Generate button, using the disabled reason as its tooltip."""
    reason = _generate_disabled_reason()
    if reason is None:
        generate_btn.enable()
        generate_tooltip.text = ''
    else:
        generate_btn.disable()
        generate_tooltip.text = reason


def _update_compile_button() -> None:
    """Enable or disable the Compile button and set its tooltip to the reason.

    Disabled when no config has been generated and no vLLM node is connected, while a compile or launch is in progress, or when a vision node uses a device that failed a health check.
    """
    if _last_generated['doc_id'] is None and not _connected_vllm_nodes():
        compile_btn.disable()
        compile_tooltip.text = 'Generate the config YAML first, then close its inspection dialog'
        return
    if core.app.state.compile_in_progress:
        compile_btn.disable()
        compile_tooltip.text = 'Compile/launch already in progress -- please wait for it to finish'
        return
    used_devices = {
        dev for n in current_graph['nodes']
        if n.get('data', {}).get('kind') == 'vision'
        for dev in _node_device_indices(n['data'])
    }
    blocked = sorted(used_devices & _unhealthy_devices)
    if blocked:
        compile_btn.disable()
        compile_tooltip.text = f'Device(s) {blocked} failed a health check -- pick a different device, or click Compile again to re-check'
    else:
        compile_btn.enable()
        compile_tooltip.text = ''




def _on_generate_clicked() -> None:
    """Build the config YAML for the current graph and show it in a save dialog.

    On a validation error shows a toast instead. Saving writes the file via _save_yaml, remembers it in _last_generated and refreshes the Compile button.
    """
    try:
        text, doc_id, kind = _build_yaml()
    except (ValueError, ValidationError) as exc:
        ui.notify(str(exc), type='negative', multi_line=True, timeout=8000)
        return

    def _on_save_clicked() -> None:
        """Save the generated YAML under the typed file name, then close the dialog."""
        try:
            out_path = _save_yaml(text, filename_input.value)
        except ValueError as exc:
            ui.notify(str(exc), type='negative')
            return
        dialog.close()
        _last_generated.update(doc_id=doc_id, kind=kind, yaml_text=text, out_path=out_path)
        _update_compile_button()
        ui.notify(f'Wrote {out_path}', type='positive')

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl'):
        ui.label('Generated config YAML').classes('text-subtitle1 font-semibold')
        filename_input = ui.input('File name', value=doc_id, placeholder='e.g. my-config.yaml') \
            .props('outlined dense').classes('w-full')
        ui.label(GENERATED_CONFIGS_DIR).classes('text-caption text-grey q-mb-sm')
        ui.textarea(value=text).props('readonly outlined rows=24').classes('w-full font-mono')
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=_on_save_clicked)
    dialog.open()


def _sync_global_settings_widgets() -> None:
    """Copy GLOBAL_SETTINGS into the OpenCL, SIMD decode and restart_interval widgets."""
    opencl_switch.value = GLOBAL_SETTINGS['use_axinference_net_opencl']
    simd_switch.value = GLOBAL_SETTINGS['use_simd_decode']
    restart_number.value = GLOBAL_SETTINGS['restart_interval']


pipeline_graph.configure(sync_global_settings_widgets=_sync_global_settings_widgets)


def _apply_loaded_graph(nodes: list[dict], edges: list[dict]) -> None:
    """Replace the canvas with a loaded graph.

    Also refreshes the Generate and Compile buttons and discards the last generated config.

    Args:
        nodes (list[dict]): Canvas nodes.
        edges (list[dict]): Canvas edges.
    """
    current_graph['nodes'] = nodes
    current_graph['edges'] = edges
    flow.set_graph(nodes, edges)
    _update_generate_button()
    _last_generated.update(doc_id=None, kind=None, yaml_text=None, out_path=None)
    _update_compile_button()


def _load_config_file(path: str) -> None:
    """Load a generated config YAML onto the canvas.

    Args:
        path (str): Path of the YAML file.

    Raises:
        ValueError: If the top level is not a mapping, or it has no 'global:' section (a legacy VLM config).
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f'{os.path.basename(path)} is not a valid config YAML (expected a mapping at the top level)')
    if 'global' not in raw:
        raise ValueError(
            f"{os.path.basename(path)} has no top-level 'global:' section -- this looks like a legacy VLM "
            "config, which this GUI can no longer load (that node kind was removed)"
        )
    nodes, edges = _graph_from_vision_config(raw)
    _apply_loaded_graph(nodes, edges)


def _on_load_config_clicked() -> None:
    """Open a dialog listing the YAML files in GENERATED_CONFIGS_DIR and load the chosen one."""
    os.makedirs(GENERATED_CONFIGS_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(GENERATED_CONFIGS_DIR) if f.endswith(('.yaml', '.yml')))

    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Load Config').classes('text-subtitle1 font-semibold')
        ui.label(GENERATED_CONFIGS_DIR).classes('text-caption text-grey q-mb-sm')
        picker = None
        if not files:
            ui.label('No config YAML files found in this directory yet -- '
                      'use Generate Config YAML first.').classes('text-grey')
        else:
            picker = ui.select({f: f for f in files}, label='Config file', value=files[0]) \
                .props('dense outlined').classes('w-full')

        def _on_load() -> None:
            """Load the selected file and close the dialog, or show a toast on failure."""
            try:
                _load_config_file(os.path.join(GENERATED_CONFIGS_DIR, picker.value))
            except Exception as exc:
                ui.notify(f'Load failed: {exc}', type='negative', multi_line=True, timeout=8000)
                return
            dialog.close()
            ui.notify(f'Loaded {picker.value}', type='positive')

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            if picker is not None:
                ui.button('Load', on_click=_on_load)
    dialog.open()




async def _on_force_stop_all_clicked() -> None:
    """Ask for confirmation, then force-stop every pipeline and vLLM/LLM server on the host.

    Shows toasts reporting the killed axinferencenet_grpc pids and the stopped vLLM/LLM servers, or that none were running.
    """
    with ui.dialog() as confirm_dialog, ui.card():
        ui.label('Force-stop every pipeline and vLLM/LLM server process on this host?').classes('text-subtitle1 font-semibold')
        ui.label("This signals ALL axinferencenet_grpc processes on the machine, including ones "
                 "this GUI didn't launch and other users' runs, and stops every vLLM/LLM server "
                 "this host_server process has launched.").classes('text-body2 text-grey')
        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=confirm_dialog.close).props('flat')
            ui.button('Force stop all', on_click=lambda: confirm_dialog.submit(True)).props('color=negative')
    if not await confirm_dialog:
        return

    notif = ui.notification('Force-stopping all pipeline and vLLM/LLM processes...', spinner=True, timeout=None)
    try:
        result = await _cleanup_all_pipelines()
    except Exception as exc:
        notif.dismiss()
        ui.notify(f'Force stop failed: {exc}', type='negative', multi_line=True, timeout=12000)
        return
    notif.dismiss()

    killed = result.get('killed_pids', [])
    if killed:
        ui.notify(f'Force-stopped {len(killed)} pipeline process(es): {", ".join(str(p) for p in killed)}',
                  type='positive', timeout=6000)
    else:
        ui.notify('No axinferencenet_grpc processes were running', type='info', timeout=5000)

    killed_vllm = result.get('killed_vllm_names', [])
    if killed_vllm:
        ui.notify(f'Stopped {len(killed_vllm)} vLLM/LLM server(s): {", ".join(killed_vllm)}',
                  type='positive', timeout=6000)
    else:
        ui.notify('No tracked vLLM/LLM servers were running', type='info', timeout=5000)


example_wizards.configure(
    fetch_models=_fetch_models,
    fetch_devices=_fetch_devices,
    fetch_vllm_artifacts=_fetch_vllm_artifacts,
    fetch_devices_health=_fetch_devices_health,
    check_devices_health_batch=_check_devices_health_batch,
    start_devices_health_check=_start_devices_health_check,
    poll_devices_health_status=_poll_devices_health_status,
    fetch_cpu_topology=_fetch_cpu_topology,
    run_devices_throughput_test=_run_devices_throughput_test,
    fetch_devices_numa_plan=_fetch_devices_numa_plan,
    build_axnet_picker=_build_axnet_picker,
    render_multi_device_cores_picker=_render_multi_device_cores_picker,
    text_field=_text_field,
    number_field=_number_field,
    collect_widget_values=_collect_widget_values,
    resolve_filter_source_meta_key=_resolve_filter_source_meta_key,
    discovery_fallback_label=_discovery_fallback_label,
    apply_loaded_graph=_apply_loaded_graph,
)




async def _on_palette_select(event) -> None:
    """Handle a selection in the node palette tree.

    Example entries launch their demo wizard. Any other catalog entry adds a node, placed on a grid of 5 columns (180 px apart) starting at (50, 250) with 120 px row spacing, indexed by the running node counter.

    Args:
        event: Tree select event; event.value is the selected node key.
    """
    tree.deselect()
    if event.value == 'example-isovision':
        await _on_isovision_demo_clicked()
        return
    if event.value == 'example-two-stage-cascade':
        await _on_cascade_demo_clicked(conditional=False)
        return
    if event.value == 'example-three-stage-cascade':
        await _on_cascade_demo_clicked(conditional=True)
        return
    if event.value == 'example-iso-vllm-demo':
        await _on_iso_vllm_demo_clicked()
        return
    entry = NODE_CATALOG.get(event.value)
    if entry is None:
        return
    column = core.app.state.node_counter % 5
    row = core.app.state.node_counter // 5
    core.app.state.node_counter += 1
    node = {
        'id': f'{event.value}-{core.app.state.node_counter}',
        'position': {'x': 50 + column * 180, 'y': 250 + row * 120},
        'data': {'label': entry['label'], **entry.get('data', {})},
    }
    if 'type' in entry:
        node['type'] = entry['type']
    flow.add_node(node)



ui.colors(primary='#1b28ea', secondary='#322c75', accent='#4a54ef', dark='#121da3', negative='#e8192d')

ui.add_head_html('''
<style>
.muted-outline-btn.q-btn--outline:before { border-color: rgba(0, 0, 0, .24); }
.muted-outline-btn { color: rgba(0, 0, 0, .54); }
</style>
''')

INFERENCE_SERVER_BADGE = '/gui-static/inference-server-badge-shadow.png'

with ui.header().classes('items-center justify-between').style('background-color: #121d3d'):
    with ui.row().classes('items-center gap-3'):
        ui.image('/gui-static/axelera-ai-logo.png').classes('h-8').style('width: 169px').props('fit=contain')
        ui.image(INFERENCE_SERVER_BADGE).classes('h-8').style('width: 233px').props('fit=contain')
    with ui.tabs(value=core.app.state.active_benchmark_tab).classes('text-white') as tabs_el:
        ui.tab('Pipeline Editor')
        ui.tab('Benchmarking')
    ui.switch('Debug', on_change=_on_toggle_recording) \
        .props('color=red') \
        .tooltip('Capture every mouse/keyboard step in the browser to a JSON file for later replay (tests/replay_recording.py) -- useful for reporting bugs that are hard to describe')


async def _on_copy_client_id_clicked() -> None:
    """Copy this browser tab's client id to the clipboard.

    Uses the async Clipboard API in a secure context and falls back to a hidden textarea with execCommand('copy'). Shows the id in a toast when copying fails.
    """
    client_id = ui.context.client.id
    copy_js = f"""
        (async () => {{
            const text = {client_id!r};
            try {{
                if (navigator.clipboard && window.isSecureContext) {{
                    await navigator.clipboard.writeText(text);
                    return true;
                }}
            }} catch (e) {{}}
            try {{
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(ta);
                return ok;
            }} catch (e) {{
                return false;
            }}
        }})()
    """
    try:
        copied = await ui.run_javascript(copy_js, timeout=5.0)
    except Exception:
        copied = False
    ui.notify(
        'Client ID copied to clipboard' if copied else f'Could not copy automatically -- client ID: {client_id}',
        type='positive' if copied else 'warning',
    )


with ui.row().classes('items-center q-gutter-xs no-wrap').style(
        'position: fixed; bottom: 6px; left: 10px; z-index: 2001;'):
    ui.label(ui.context.client.id).classes('text-caption').style('opacity: 0.45;').tooltip('Client ID')
    ui.button(icon='content_copy', on_click=_on_copy_client_id_clicked) \
        .props('flat dense round size=sm color=grey') \
        .tooltip('Copy client ID')


with ui.left_drawer(value=True, fixed=True).classes('bg-grey-2 q-pa-sm') as drawer:
    search = ui.input(placeholder='Search nodes and examples ...').props('dense clearable outlined').classes('w-full q-mb-sm')
    tree = ui.tree(PALETTE_TREE, label_key='label', node_key='id', on_select=_on_palette_select).expand(['nodes', 'models'])

    ui.separator().classes('q-my-sm')
    ui.label('Global Settings').classes('text-caption text-grey') \
        .tooltip('config_schema.GlobalSettings')
    opencl_switch = ui.switch('OpenCL', value=GLOBAL_SETTINGS['use_axinference_net_opencl'],
              on_change=lambda e: GLOBAL_SETTINGS.update(use_axinference_net_opencl=e.value)) \
        .classes('w-full') \
        .tooltip("config_schema.GlobalSettings.use_axinference_net_opencl -- applies only when the canvas's model node is Vision")
    simd_switch = ui.switch('SIMD decode', value=GLOBAL_SETTINGS['use_simd_decode'],
              on_change=lambda e: GLOBAL_SETTINGS.update(use_simd_decode=e.value)) \
        .classes('w-full') \
        .tooltip('TurboJPEG SIMD decode, off = OpenCV')
    restart_number = ui.number('restart_interval', value=GLOBAL_SETTINGS['restart_interval'], min=0, format='%.0f',
               on_change=lambda e: GLOBAL_SETTINGS.update(restart_interval=int(e.value or 0))) \
        .props('dense outlined').classes('w-full') \
        .tooltip('restart_interval (s, 0 = disabled)')
    tree.bind_filter_from(search, 'value')


with ui.column().classes('w-full relative') as pipeline_view:
    flow = PipelineFlow(
        nodes=current_graph['nodes'], edges=current_graph['edges'],
        on_graph_changed=_on_graph_changed, on_debug_event=_on_debug_event, on_node_dblclick=_on_node_dblclick,
    )
    node_dialogs.configure(
        flow_=flow,
        check_devices_health_batch=_check_devices_health_batch,
        download_prebuilt_model=_download_prebuilt_model,
        fetch_devices=_fetch_devices,
        fetch_models=_fetch_models,
        fetch_prebuilt_models=_fetch_prebuilt_models,
        fetch_vllm_artifacts=_fetch_vllm_artifacts,
        render_detected_meta_key_field=_render_detected_meta_key_field,
        resolve_filter_source_meta_key=_resolve_filter_source_meta_key,
        update_compile_button=_update_compile_button,
    )
    with ui.row().classes('absolute bottom-4 right-4 gap-2'):
        ui.button('Load Config', icon='folder_open', on_click=_on_load_config_clicked) \
            .classes('shadow-4') \
            .tooltip('Load a previously generated config YAML from generated_configs/, replacing the current canvas')
        generate_btn = ui.button('Generate Config YAML', icon='bolt', on_click=_on_generate_clicked) \
            .classes('shadow-4')
        with generate_btn:
            generate_tooltip = ui.tooltip('')

        compile_btn = ui.button('Compile and Launch Pipeline', icon='build', on_click=_on_compile_clicked) \
            .classes('shadow-4')
        with compile_btn:
            compile_tooltip = ui.tooltip('')

        ui.button('Force Stop All', icon='dangerous', on_click=_on_force_stop_all_clicked) \
            .classes('shadow-4').props('color=negative') \
            .tooltip('Nuclear option: SIGTERM/SIGKILL every axinferencenet_grpc process on this host, '
                     'any pipeline, any user -- no config needed (POSTs /api/v1/pipelines/cleanup-all)')
    _update_generate_button()
    _update_compile_button()
CANVAS_SHORTCUTS = [
    'Double-click an Input/Vision/Sink node to edit its config',
    'Click a node to select it',
    'Ctrl/Cmd+click a node to add it to the current selection (a plain click would replace it)',
    'Shift+drag an empty area to box-select everything inside it',
    'Ctrl/Cmd+C to copy the selection (including links between selected nodes), click where you want it, then Ctrl/Cmd+V to paste it there',
    'Right-click a node, or press Backspace/Delete, to remove the selection',
    'Ctrl/Cmd+Z to undo the last paste or link replacement',
    'Dragging a new link onto an already-linked handle replaces its old link',
]
shortcuts_label = ui.label('\n'.join(CANVAS_SHORTCUTS)) \
    .classes('w-full text-center text-caption text-grey q-mt-xs') \
    .style('white-space: pre-line')

with ui.column().classes('w-full h-full gap-0') as benchmarking_view:
    with ui.row().classes('w-full no-wrap gap-4 q-pa-md items-start'):
        with ui.column().classes('q-pa-sm gap-2').style('width: 320px; min-width: 320px; border: 1px solid #ddd'):
            with ui.row().classes('w-full items-center gap-2'):
                ui.label('Sources').classes('text-subtitle1')
                benchmark_source_count_label = ui.label('0').classes('text-caption text-grey')
            with ui.row().classes('w-full gap-2'):
                ui.button('Add file', icon='add_photo_alternate', on_click=_on_benchmark_add_file_clicked).props('dense outline')
                ui.button('Add webcam', icon='videocam', on_click=_on_benchmark_add_webcam_clicked).props('dense outline')
                ui.button(icon='delete_sweep', on_click=_on_benchmark_remove_all_clicked) \
                    .props('dense color=negative').tooltip('Remove all sources')
            sources_container = ui.column().classes('w-full gap-2')
        with ui.column().classes('col q-pa-sm gap-2').style(
                'border: 1px dashed #bbb; position: sticky; top: 12px; z-index: 10'):
            ui.label('Live stats').classes('text-subtitle1 text-grey')
            benchmark_no_sources_label = ui.label(
                'No active inference sources yet -- add a source with an inference endpoint configured (Advanced Settings) to see graphs.') \
                .classes('text-caption text-grey')
            benchmark_stats_plot = ui.plotly({'data': [], 'layout': _benchmark_combined_plot_layout()}).classes('w-full')
            with ui.row().classes('w-full justify-end q-mt-none'):
                ui.button(icon='refresh', on_click=_on_benchmark_clear_plot_clicked) \
                    .props('dense flat round size=sm aria-label="plot refresh"') \
                    .tooltip('Clear plot (reset to a fresh-restart empty state)')
            ui.separator().classes('q-my-sm')
            with ui.column().classes('w-full gap-2'):
                ui.label('(V/L)LM Chat').classes('text-subtitle1')
                ui.label(
                    "Chat with a (V/L)LM server launched from the Pipeline Editor tab's (V/L)LM node -- "
                    'attach image(s) for a VLM call, or leave them off for a text-only LLM call.'
                ).classes('text-caption text-grey')
                with ui.row().classes('w-full items-center gap-2'):
                    chat_endpoint_select = ui.select({}, label='(V/L)LM server', on_change=lambda e: _chat_activate_session(e.value)) \
                        .props('dense outlined').classes('col') \
                        .tooltip('Each server gets its own isolated chat session -- switching here never '
                                 "mixes histories, and a session's Play loop keeps running in the background "
                                 'if you switch away from it')
                    ui.button(icon='refresh', on_click=_chat_refresh_groups, color=None) \
                        .props('dense outline aria-label="chat refresh"').classes('muted-outline-btn') \
                        .tooltip('Refresh running (V/L)LM servers')
                    chat_concurrency_input = ui.number('Concurrent requests', value=1, min=1, max=32, format='%.0f') \
                        .props('dense outlined').style('width: 180px') \
                        .tooltip('Fans the same message out as this many concurrent requests, round-robined '
                                 "across the selected node's running instance(s) -- simulates concurrent users")
                    chat_max_tokens_input = ui.number('Max new tokens', value=128, min=1, max=4096, format='%.0f') \
                        .props('dense outlined').style('width: 160px') \
                        .tooltip('Answer-length budget sent as max_tokens -- without a cap, a reply that never '
                                 'hits a natural stop keeps generating until the context limit, which on this '
                                 "backend's one-token-at-a-time decode can look like the chat box hanging")
                chat_log = ui.scroll_area().classes('w-full').style('height: 220px; border: 1px solid #eee')
                with ui.row().classes('w-full items-center gap-2'):
                    ui.label('Prompt library').classes('text-caption text-grey')
                    ui.button(icon='add', on_click=_on_prompt_library_open_clicked, color=None) \
                        .props('dense outline round size=sm').classes('muted-outline-btn') \
                        .tooltip('Add a prompt to your library')
                    play_btn = ui.button(on_click=_on_prompt_library_play_clicked, color=None) \
                        .props(_PLAY_BTN_IDLE_PROPS).classes('muted-outline-btn') \
                        .tooltip('Loop selected prompts (ticked + Saved) against the current (V/L)LM server -- '
                                 'click again to stop. Keeps running in the background if you switch to a '
                                 'different server; switching back shows its current state')
                with ui.row().classes('w-full items-center gap-2'):
                    ui.button('Add image(s)', icon='add_photo_alternate', on_click=_on_chat_add_image_clicked, color=None) \
                        .props('dense outline').classes('muted-outline-btn')
                    chat_images_label = ui.label(f'0/{CHAT_MAX_IMAGES} images attached ({CHAT_MAX_IMAGES} more allowed)') \
                        .classes('text-caption text-grey')
                chat_images_row = ui.row().classes('w-full gap-2 flex-wrap')
                chat_text_input = ui.textarea(
                    label='Message', placeholder='Type a message...', on_change=_on_chat_text_changed,
                ).props('dense outlined autogrow').classes('w-full')
                chat_budget_label = ui.label('').classes('text-caption text-grey')
                with ui.row().classes('w-full items-center justify-between gap-2'):
                    chat_metrics_label = ui.label('').classes('text-caption text-grey')
                    with ui.row().classes('gap-2'):
                        ui.button('Clear', on_click=_on_chat_clear_clicked).props('flat')
                        send_btn = ui.button('Send', icon='send', on_click=_on_chat_send_clicked)
    chat.configure(
        chat_endpoint_select_=chat_endpoint_select, chat_max_tokens_input_=chat_max_tokens_input,
        chat_concurrency_input_=chat_concurrency_input, chat_log_=chat_log, play_btn_=play_btn,
        send_btn_=send_btn, chat_images_label_=chat_images_label, chat_images_row_=chat_images_row,
        chat_text_input_=chat_text_input, chat_budget_label_=chat_budget_label,
        chat_metrics_label_=chat_metrics_label,
    )
    # Polls three times per debounce interval.
    _chat_token_budget_timer = ui.timer(CHAT_TOKEN_DEBOUNCE_S / 3, _chat_token_budget_tick)
    ui.timer(0.1, _chat_refresh_groups, once=True)
benchmarking_view.set_visibility(False)
_benchmark_drain_timer = ui.timer(BENCHMARK_DRAIN_INTERVAL_S, _benchmark_drain_tick)
_benchmark_metrics_timer = ui.timer(BENCHMARK_METRICS_SAMPLE_INTERVAL_S, _benchmark_metrics_tick)
_monitor_stats_timer = ui.timer(MONITOR_METRICS_SAMPLE_INTERVAL_S, _monitor_stats_tick)

with ui.right_drawer(value=False, fixed=True, elevated=True).classes('bg-grey-2 q-pa-md scroll') \
        .props('aria-label="benchmark settings drawer"') as benchmark_settings_drawer:
    ui.label('Advanced Settings').classes('text-subtitle2 font-semibold q-mb-sm')
    benchmark_endpoint_input = ui.input(
        label='Inference endpoint(s)',
        placeholder='host:port, host2:port2, ...',
        value=', '.join(_benchmark_endpoints),
        on_change=lambda e: _on_benchmark_endpoints_changed(e.value),
    ).props('dense outlined').classes('w-full') \
        .tooltip('AxVisionClient endpoint(s) (comma-separated) to run real inference '
                 'against. Only applies to sources added after this is set -- '
                 'empty means capture/display only, no inference. Auto-filled from '
                 'the port(s) a successful Compile and Launch Pipeline just launched; '
                 'edit freely to point elsewhere.')
    benchmark_pipeline_id_input = ui.input(
        label='Pipeline ID(s) for backpressure monitoring',
        placeholder='pipeline-id, pipeline-id-2, ...',
        value=', '.join(_benchmark_pipeline_ids),
        on_change=lambda e: _on_benchmark_pipeline_ids_changed(e.value),
    ).props('dense outlined').classes('w-full') \
        .tooltip('Optional: host_server.py pipeline_id(s) matching the endpoint(s) '
                 'above. When set, sources added after this slow their own send rate '
                 '(AIMD-style) in response to host_server.py\'s /queue-stats '
                 'backpressure signal for these pipelines. Leave empty to disable -- '
                 'sources behave exactly as before. Auto-filled from a successful '
                 'Compile and Launch Pipeline, same as Inference endpoint(s) above.')
    ui.label('Live stats series').classes('text-caption text-grey q-mt-sm')
    ui.checkbox('Aggregate FPS', value=_benchmark_show_aggregate_fps,
                on_change=lambda e: _on_benchmark_show_aggregate_fps_changed(e.value)).classes('w-full')
    benchmark_aggregate_fps_filter_mode_toggle = ui.radio(
        {'ema': 'EMA', 'hampel': 'Hampel'},
        value=_benchmark_aggregate_fps_filter_mode,
        on_change=lambda e: _on_benchmark_aggregate_fps_filter_mode_changed(e.value),
    ).props('dense inline').classes('w-full q-pl-md') \
        .tooltip('Which filter smooths/cleans the Aggregate FPS line. EMA is a '
                 'standard exponential moving average (smooths everything, lags '
                 'behind real changes). Hampel is an outlier-replacement filter: it '
                 'leaves normal variation untouched and only clamps points that are '
                 'statistical outliers relative to their local neighborhood, so a '
                 'momentary spike gets replaced without smearing the rest of the '
                 'curve.')
    benchmark_aggregate_fps_ema_alpha_input = ui.number(
        label='Aggregate FPS EMA alpha',
        value=_benchmark_aggregate_fps_ema_alpha,
        min=0.01,
        max=1.0,
        step=0.01,
        on_change=lambda e: _on_benchmark_aggregate_fps_ema_alpha_changed(e.value),
    ).props('dense outlined').classes('w-full q-pl-md') \
        .tooltip('Smoothing factor for the Aggregate FPS line\'s exponential moving '
                 'average: smoothed = alpha * new + (1 - alpha) * previous. 1.0 '
                 'disables smoothing (raw per-tick sum); lower values smooth more '
                 'but lag further behind real changes. Recomputed from the full '
                 'buffered history on every change, so it reshapes the whole '
                 'visible curve immediately.')
    benchmark_aggregate_fps_hampel_window_input = ui.number(
        label='Hampel window size',
        value=_benchmark_aggregate_fps_hampel_window,
        min=3,
        step=2,
        on_change=lambda e: _on_benchmark_hampel_window_changed(e.value),
    ).props('dense outlined').classes('w-full q-pl-md') \
        .tooltip('Number of neighboring samples (centered on each point) used to '
                 'compute the local median/MAD an outlier is compared against. '
                 'Rounded up to the next odd number if even. Larger windows '
                 'consider more context but react more slowly to genuine, sustained '
                 'changes in FPS.')
    benchmark_aggregate_fps_hampel_nsigmas_input = ui.number(
        label='Hampel n-sigmas',
        value=_benchmark_aggregate_fps_hampel_nsigmas,
        min=0.1,
        step=0.1,
        on_change=lambda e: _on_benchmark_hampel_nsigmas_changed(e.value),
    ).props('dense outlined').classes('w-full q-pl-md') \
        .tooltip('How many robust standard deviations (MAD-based) a point must '
                 'deviate from its local median before it is treated as an outlier '
                 'and replaced. Lower values flag more points as outliers (more '
                 'aggressive filtering).')
    benchmark_aggregate_fps_ema_alpha_input.set_visibility(_benchmark_aggregate_fps_filter_mode == 'ema')
    benchmark_aggregate_fps_hampel_window_input.set_visibility(_benchmark_aggregate_fps_filter_mode == 'hampel')
    benchmark_aggregate_fps_hampel_nsigmas_input.set_visibility(_benchmark_aggregate_fps_filter_mode == 'hampel')
    ui.checkbox('Per-source FPS', value=_benchmark_show_per_source_fps,
                on_change=lambda e: _on_benchmark_show_per_source_fps_changed(e.value)).classes('w-full')
    ui.checkbox('Per-source latency', value=_benchmark_show_per_source_latency,
                on_change=lambda e: _on_benchmark_show_per_source_latency_changed(e.value)).classes('w-full')
    ui.checkbox('Per-source errors', value=_benchmark_show_per_source_error,
                on_change=lambda e: _on_benchmark_show_per_source_error_changed(e.value)).classes('w-full')
    ui.checkbox('Aggregate errors', value=_benchmark_show_aggregate_error,
                on_change=lambda e: _on_benchmark_show_aggregate_error_changed(e.value)).classes('w-full')
    ui.checkbox('CPU utilization', value=_benchmark_show_cpu_percent,
                on_change=lambda e: _on_benchmark_show_cpu_percent_changed(e.value)).classes('w-full') \
        .tooltip('Host-wide CPU utilization (%), not per source. Plotted on its own '
                 'right-hand % axis so it never disturbs the fps/error or latency axes.')
    ui.checkbox('Per-core CPU utilization', value=_benchmark_show_cpu_percent_percore,
                on_change=lambda e: _on_benchmark_show_cpu_percent_percore_changed(e.value)).classes('w-full') \
        .tooltip('Adds one line per logical core to the chart above (shares the '
                 'CPU/memory %% axis). Can get busy on a many-core host.')
    ui.checkbox('Memory utilization', value=_benchmark_show_mem_percent,
                on_change=lambda e: _on_benchmark_show_mem_percent_changed(e.value)).classes('w-full') \
        .tooltip('Host-wide memory utilization (%), not per source. Shares the CPU '
                 'utilization checkbox\'s % axis.')
    ui.label('AxMonitor device stats').classes('text-caption text-grey q-mt-sm')
    _monitor_checkbox_tooltip_suffix = (
        ' Grayed out until axmonitor/axsystemserver are confirmed reachable -- '
        'if this stays disabled, re-run setup.sh with --monitor and restart the '
        'container/host_server.')
    monitor_aggregate_core_checkbox = ui.checkbox(
        'Aggregate core utilization %', value=_benchmark_show_monitor_aggregate_core,
        on_change=lambda e: _on_benchmark_show_monitor_aggregate_core_changed(e.value),
    ).classes('w-full').tooltip(
        'One line: every device\'s every AI core\'s utilization %%, summed and '
        'normalized across (devices * 4 cores) into a single aggregate %%.'
        + _monitor_checkbox_tooltip_suffix)
    monitor_aggregate_mvm_checkbox = ui.checkbox(
        'Aggregate MVM utilization %', value=_benchmark_show_monitor_aggregate_mvm,
        on_change=lambda e: _on_benchmark_show_monitor_aggregate_mvm_changed(e.value),
    ).classes('w-full').tooltip(
        'One line: every device\'s every AI core\'s MVM (average) utilization %%, '
        'summed and normalized across (devices * 4 cores) into a single '
        'aggregate %%.' + _monitor_checkbox_tooltip_suffix)
    monitor_aggregate_syscore_checkbox = ui.checkbox(
        'Aggregate sys-core utilization %', value=_benchmark_show_monitor_aggregate_syscore,
        on_change=lambda e: _on_benchmark_show_monitor_aggregate_syscore_changed(e.value),
    ).classes('w-full').tooltip(
        'One line: every device\'s sys-core utilization %%, averaged across '
        'however many devices are present.' + _monitor_checkbox_tooltip_suffix)
    monitor_aggregate_ddr_checkbox = ui.checkbox(
        'Aggregate DDR utilization %', value=_benchmark_show_monitor_aggregate_ddr,
        on_change=lambda e: _on_benchmark_show_monitor_aggregate_ddr_changed(e.value),
    ).classes('w-full').tooltip(
        'One line: every device\'s DDR utilization %%, averaged across however '
        'many devices are present.' + _monitor_checkbox_tooltip_suffix)
    monitor_per_device_raw_checkbox = ui.checkbox(
        'Plot all AxMonitor stats per device (raw)', value=_benchmark_show_monitor_per_device_raw,
        on_change=lambda e: _on_benchmark_show_monitor_per_device_raw_changed(e.value),
    ).classes('w-full').tooltip(
        'Unaggregated: one line per device for DDR %% and sys-core %%, plus one '
        'line per device per AI core for core %% and MVM %% -- e.g. "Dev 0 core '
        '2 %%". Same idea as Per-core CPU utilization above, just for AxMonitor '
        'device stats instead of host CPU.' + _monitor_checkbox_tooltip_suffix)
    monitor_power0_checkbox = ui.checkbox(
        'Power sensor 0 (W)', value=_benchmark_show_monitor_power_sensor_0,
        on_change=lambda e: _on_benchmark_show_monitor_power_sensor_0_changed(e.value),
    ).classes('w-full').tooltip(
        'Measured average power from AxMonitor\'s power sensor 0, summed over all devices that report it '
        '(one line), on its own W axis. Devices without this sensor are skipped.'
        + _monitor_checkbox_tooltip_suffix)
    monitor_power1_checkbox = ui.checkbox(
        'Power sensor 1 (W)', value=_benchmark_show_monitor_power_sensor_1,
        on_change=lambda e: _on_benchmark_show_monitor_power_sensor_1_changed(e.value),
    ).classes('w-full').tooltip(
        'Measured average power from AxMonitor\'s power sensor 1, summed over all devices that report it '
        '(one line), on its own W axis. Devices without this sensor are skipped.'
        + _monitor_checkbox_tooltip_suffix)
    _MONITOR_CHECKBOXES.extend([
        monitor_aggregate_core_checkbox, monitor_aggregate_mvm_checkbox,
        monitor_aggregate_syscore_checkbox, monitor_aggregate_ddr_checkbox,
        monitor_per_device_raw_checkbox, monitor_power0_checkbox, monitor_power1_checkbox,
    ])
    with ui.row().classes('w-full items-center no-wrap q-mt-sm q-gutter-xs'):
        monitor_power_device_input = ui.number(
            label='Device', value=0, min=0, step=1, format='%.0f',
        ).props('dense outlined').classes('col').tooltip('Device ID, as numbered by axdevice / the device list.')
        monitor_power_limit_input = ui.number(
            label='Power (W)', value=0, min=0, max=MONITOR_POWER_LIMIT_MAX_W, step=1,
        ).props('dense outlined').classes('col').tooltip(
            f'Power limit in watts, 0-{MONITOR_POWER_LIMIT_MAX_W:g}; 0 = off (no limit). '
            'Applied live with axdevice --set-power-limit, even while pipelines run.')
        monitor_power_set_button = ui.button(
            'Set', on_click=lambda: _on_monitor_set_power_clicked(
                monitor_power_device_input, monitor_power_limit_input),
        ).props('dense').tooltip('Set this device\'s power limit.')
    # AxMonitor checkboxes stay disabled until the monitor is known to be reachable.
    for _cb in _MONITOR_CHECKBOXES:
        _cb.disable()
    if core.app.state.monitor_available is not None:
        _update_monitor_checkbox_availability(core.app.state.monitor_available)
    benchmark_history_maxlen_input = ui.number(
        label='History buffer (samples per source)',
        value=_benchmark_metrics_history_maxlen,
        min=10,
        max=100000,
        step=10,
        on_change=lambda e: _on_benchmark_history_maxlen_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('How many fps/latency/error samples each source keeps for the '
                 'Live stats chart above, sampled once every '
                 f'{BENCHMARK_METRICS_SAMPLE_INTERVAL_S:g}s -- e.g. 1000 samples is '
                 'a ~33 min rolling window per source. Shrinking this immediately '
                 'trims every currently-active source down to its most recent '
                 'samples; growing it only affects how much history accumulates '
                 'from now on.')
    benchmark_thumbnail_interval_input = ui.number(
        label='Thumbnail refresh interval (s)',
        value=_benchmark_thumbnail_refresh_interval_s,
        min=1,
        max=60,
        step=1,
        on_change=lambda e: _on_benchmark_thumbnail_interval_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('How often each source tile\'s small thumbnail in the left panel '
                 're-fetches the latest saved frame -- a plain HTTP GET, independent '
                 'of its actual capture/inference rate, so this can be slow (it\'s '
                 'fine for it to lag several seconds behind). Click a tile to open '
                 'its pinned view instead, which streams real-time detections for '
                 'that one source over MJPEG regardless of this setting. Applies '
                 'immediately to all existing sources.')
    benchmark_stream_fps_input = ui.number(
        label='Stream FPS cap',
        value=_BENCHMARK_STREAM_SETTINGS['fps'],
        min=1,
        max=60,
        step=1,
        on_change=lambda e: _on_benchmark_stream_fps_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('Caps how often the pinned preview\'s MJPEG stream polls for a '
                 'new frame to send over the network -- lower this to save '
                 'bandwidth on a slow/remote connection (e.g. over Tailscale). '
                 'Applies immediately to already-open pinned streams.')
    benchmark_stream_max_width_input = ui.number(
        label='Disk save max width (px, 0 = original)',
        value=_BENCHMARK_STREAM_SETTINGS['max_width_px'],
        min=0,
        max=3840,
        step=1,
        on_change=lambda e: _on_benchmark_stream_max_width_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('Downscales rendered frames to this width (aspect ratio '
                 'preserved) before writing them to the on-disk ring buffer '
                 '-- the archived resolution, used by both the pinned stream '
                 'and grid thumbnail unless overridden below. 0 keeps the '
                 'source\'s native capture resolution. Only affects frames '
                 'saved after this is changed.')
    benchmark_backpressure_input = ui.number(
        label='Backpressure cap (in-flight inference requests)',
        value=_BENCHMARK_STREAM_SETTINGS['max_pending_inflight'],
        min=0,
        max=1000,
        step=1,
        on_change=lambda e: _on_benchmark_backpressure_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('Max frames a source may have submitted for inference and '
                 'still awaiting a result before it starts skipping new '
                 'frames instead of piling them up in memory -- each '
                 'in-flight frame holds a full-resolution raw copy until its '
                 'result arrives. This is the same concurrency knob as '
                 '--in-flight in the AxVisionClient stress-test tool: it '
                 'governs throughput, not just memory, since a pipeline\'s '
                 'achievable fps rises with concurrency up to a ceiling '
                 'then flat-lines or degrades past it (the exact ceiling '
                 'depends on the compiled pipeline\'s own queue_depth, a '
                 'separate server-side setting). Unlike the stress tool, '
                 'which blocks and waits for a slot once the cap is hit, '
                 'this source drops the new frame instead. Lower this if '
                 'inference is falling behind capture (saturated endpoint, '
                 'several sources sharing one device) and memory keeps '
                 'climbing; raise it to find the pipeline\'s true throughput '
                 'ceiling or tolerate a longer burst of latency before '
                 'frames start dropping. 0 disables the cap entirely '
                 '(unbounded backlog -- can grow memory unboundedly if '
                 'inference falls behind). Only applies to sources added '
                 'after this is changed.')
    benchmark_request_timeout_input = ui.number(
        label='Client request timeout (s)',
        value=_BENCHMARK_STREAM_SETTINGS['request_timeout_sec'],
        min=0.1,
        step=1,
        on_change=lambda e: _on_benchmark_request_timeout_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('AxVisionClient\'s own client-side gRPC call deadline for '
                 'this source -- separate from the pipeline\'s server-side '
                 '"timeout" field (Pipeline Editor -> Input node -> Advanced '
                 'Settings). Must be set >= the pipeline\'s server-side '
                 'timeout, or this client gives up and logs a "client-side '
                 'DEADLINE_EXCEEDED" before the server ever gets a chance to '
                 'honor its own longer timeout. Only applies to sources '
                 'added after this is changed.')
    benchmark_aimd_backoff_switch = ui.switch(
        'AIMD backoff',
        value=_BENCHMARK_STREAM_SETTINGS['aimd_backoff_enabled'],
        on_change=lambda e: _on_benchmark_aimd_backoff_changed(e.value),
    ).classes('w-full q-mt-sm') \
        .tooltip('When on, a source watches /queue-stats and self-throttles '
                 '(capture interval divided by a growing backoff_multiplier, '
                 'shown as a ÷X.X badge on its tile) while the backend '
                 'looks congested, recovering gradually once it clears. Turn '
                 'off to let a source flood an already-congested backend at '
                 'its full requested fps instead of self-throttling -- useful '
                 'for deliberately reproducing/measuring saturation behavior '
                 'without the client masking it. Only applies to sources '
                 'added after this is changed.')
    ui.label('Pinned stream (network) overrides').classes('text-caption text-grey q-mt-sm')
    ui.radio(
        {'native': 'Native', '720p': '720p', '480p': '480p', '360p': '360p'},
        value=_BENCHMARK_STREAM_SETTINGS['resolution_preset'],
        on_change=lambda e: _on_benchmark_stream_resolution_changed(e.value),
    ).props('inline dense').classes('w-full') \
        .tooltip('Resolution the pinned preview is served at over the '
                 'network -- resizes on the fly at serve time, independent '
                 'of whatever resolution is archived to disk above. '
                 '"Native" sends the saved frame unresized. Lower this to '
                 'cut bandwidth without touching the on-disk archive. '
                 'Applies immediately to already-open pinned streams.')
    benchmark_stream_quality_input = ui.number(
        label='Stream quality (1-100)',
        value=_BENCHMARK_STREAM_SETTINGS['quality'],
        min=1,
        max=100,
        step=1,
        on_change=lambda e: _on_benchmark_stream_quality_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('JPEG/WebP quality the pinned preview is re-encoded at over '
                 'the network. Lower = smaller frames, more compression '
                 'artifacts. Only triggers a re-encode (and so only takes '
                 'effect) once it differs from the default, or resolution/'
                 'format below is also changed -- does not affect the '
                 'on-disk archive. Applies immediately to already-open '
                 'pinned streams.')
    ui.radio(
        {'jpeg': 'Motion JPEG', 'webp': 'WebP'},
        value=_BENCHMARK_STREAM_SETTINGS['format'],
        on_change=lambda e: _on_benchmark_stream_format_changed(e.value),
    ).props('inline dense').classes('w-full q-mt-sm') \
        .tooltip('Wire format for the pinned preview\'s network stream. '
                 'WebP runs roughly 30% smaller than JPEG at the same '
                 'quality on real footage, but relies on the browser\'s '
                 '<img> decoder accepting image/webp parts inside a '
                 'multipart stream -- fall back to Motion JPEG if a '
                 'pinned preview stops updating after switching. Applies '
                 'immediately to already-open pinned streams.')
    benchmark_playback_delay_input = ui.number(
        label='Playback delay (seconds)',
        value=_benchmark_stream_playback_delay_s,
        min=0,
        max=10,
        step=0.5,
        on_change=lambda e: _on_benchmark_playback_delay_changed(e.value),
    ).props('dense outlined').classes('w-full q-mt-sm') \
        .tooltip('How far behind each frame\'s own capture time the pinned '
                 'stream dialog holds playback, pacing frames out using '
                 'their original capture cadence rather than network '
                 'arrival order. 2s (default) smooths over brief network '
                 'hiccups/bursts at the cost of added display latency. A '
                 'stall longer than this empties the buffer and shows a '
                 '"rebuffering" status until fresh frames catch back up to '
                 'live. Takes effect immediately on already-open pinned '
                 'streams.')
benchmark_settings_drawer.on('mouseleave', lambda: benchmark_settings_drawer.hide())

benchmark.configure(
    benchmark_aggregate_fps_ema_alpha_input_=benchmark_aggregate_fps_ema_alpha_input,
    benchmark_aggregate_fps_hampel_nsigmas_input_=benchmark_aggregate_fps_hampel_nsigmas_input,
    benchmark_aggregate_fps_hampel_window_input_=benchmark_aggregate_fps_hampel_window_input,
    benchmark_no_sources_label_=benchmark_no_sources_label,
    benchmark_source_count_label_=benchmark_source_count_label,
    benchmark_stats_plot_=benchmark_stats_plot,
    sources_container_=sources_container,
)
_rehydrate_benchmark_sources()

pipeline_compile.configure(
    compile_btn_=compile_btn,
    compile_tooltip_=compile_tooltip,
    benchmark_endpoint_input_=benchmark_endpoint_input,
    benchmark_pipeline_id_input_=benchmark_pipeline_id_input,
    update_compile_button=_update_compile_button,
)

# Invisible 16 px strip on the right viewport edge; hovering it opens the settings drawer. Only shown on the Benchmarking tab.
benchmark_settings_edge_sensor = ui.element('div').style(
    'position: fixed; top: 0; right: 0; width: 16px; height: 100vh; z-index: 2001;'
).props('aria-label="benchmark settings edge"')
benchmark_settings_edge_sensor.on('mouseenter', lambda: benchmark_settings_drawer.show())
benchmark_settings_edge_sensor.set_visibility(False)


def _apply_tab_visibility(tab_name: str) -> None:
    """Show the widgets that belong to the selected tab and hide the rest.

    Args:
        tab_name (str): 'Pipeline Editor' or 'Benchmarking'.
    """
    is_pipeline = tab_name == 'Pipeline Editor'
    is_benchmarking = tab_name == 'Benchmarking'
    if is_pipeline:
        drawer.show()
    else:
        drawer.hide()
    pipeline_view.set_visibility(is_pipeline)
    shortcuts_label.set_visibility(is_pipeline)
    benchmarking_view.set_visibility(is_benchmarking)
    benchmark_settings_edge_sensor.set_visibility(is_benchmarking)
    if not is_benchmarking:
        benchmark_settings_drawer.hide()


def _on_tab_change(e) -> None:
    """Remember the selected tab in app state and apply its visibility.

    Args:
        e: Tab change event; e.value is the tab name.
    """
    core.app.state.active_benchmark_tab = e.value
    _apply_tab_visibility(e.value)


tabs_el.on_value_change(_on_tab_change)
_apply_tab_visibility(core.app.state.active_benchmark_tab)

ui.add_head_html(
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>'
)

app.add_static_files('/gui-static', os.path.join(os.path.dirname(__file__), 'static'))

ui.add_head_html(f'''
<link rel="stylesheet" href="/gui-static/benchmark_stream.css">
<script>
window.__pinnedStreamPlaybackDelayMs = window.__pinnedStreamPlaybackDelayMs || {_benchmark_stream_playback_delay_s * 1000.0};
</script>
<script src="/gui-static/benchmark_stream.js"></script>
''')

_annotate_asset_dir = Path(__file__).parent / 'static'
# Cache-busting query value: newest mtime of the annotate overlay assets.
_annotate_asset_v = int(max(
    (_annotate_asset_dir / 'annotate_overlay.css').stat().st_mtime,
    (_annotate_asset_dir / 'annotate_overlay.js').stat().st_mtime,
))
ui.add_head_html(f'''
<link rel="stylesheet" href="/gui-static/annotate_overlay.css?v={_annotate_asset_v}">
<script src="/gui-static/annotate_overlay.js?v={_annotate_asset_v}"></script>
''')

@app.on_shutdown
def _stop_all_benchmark_workers() -> None:
    """Stop every benchmark worker process on shutdown: signal stop, join for 3 s, then terminate stragglers."""
    for entry in list(BENCHMARK_SOURCES.values()):
        entry['stop_event'].set()
    for entry in list(BENCHMARK_SOURCES.values()):
        process = entry['process']
        process.join(timeout=3.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)


import agent_surface
agent_surface.configure(
    read_file_bytes=_read_file_bytes,
    benchmark_ring_buffer_names=_benchmark_ring_buffer_names,
)

ui.run(
    title='No-Code Pipeline Editor',
    host=os.environ.get('GUI_APP_HOST', '0.0.0.0'),
    port=int(os.environ.get('GUI_APP_PORT', 8080)),
    reload=False,
)
