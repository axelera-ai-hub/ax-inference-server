"""Host-server client calls and the Compile and Launch flow of the Pipeline Editor.

Wraps the host server REST API (models, devices, health checks, NUMA plans, pipeline upload/launch/shutdown, vLLM launch) and provides `_on_compile_clicked`, which compiles the generated config locally, provisions models, checks device health, uploads the specs and launches the pipelines.

Note:
    Needs `HOST_SERVER_URL` (and `HOST_SERVER_API_KEY`) in the environment. The fetch helpers return a dict with a `reachable` flag instead of raising; the pipeline launch helpers raise `RuntimeError` when the URL is not configured and `httpx` errors on HTTP failures.
    Widgets are injected through `configure()`.
"""


import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import yaml
from nicegui import core, ui

from benchmark import _on_benchmark_endpoints_changed, _on_benchmark_pipeline_ids_changed
from chat import _chat_refresh_groups
from config_schema import ServerConfig, load_config as load_vision_config
from node_catalog import CORES_PER_DEVICE
from pipeline import PipelineCompiler
from pipeline_graph import (
    _axnet_catalog_name, _connected_vllm_nodes, _node_device_indices, _predecessors,
    _read_axnet_default_meta_key, _vllm_node_devices,
)

HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')

# Local output folder of compiled pipeline specs (one subfolder per document id).
COMPILED_SPECS_DIR = os.path.join(os.path.dirname(__file__), 'compiled_specs')

# App-wide state shared with app.py and the graph module.
GLOBAL_SETTINGS: dict = core.app.state.global_settings
current_graph: dict = core.app.state.current_graph

# Result of the last YAML generation: document id, pipeline kind, YAML text and output path.
if not hasattr(core.app.state, 'last_generated'):
    core.app.state.last_generated = {'doc_id': None, 'kind': None, 'yaml_text': None, 'out_path': None}
_last_generated: dict = core.app.state.last_generated

if not hasattr(core.app.state, 'unhealthy_devices'):
    core.app.state.unhealthy_devices = set()
_unhealthy_devices: set[int] = core.app.state.unhealthy_devices

# Injected by configure().
compile_btn = None
compile_tooltip = None
benchmark_endpoint_input = None
benchmark_pipeline_id_input = None
_update_compile_button = None

def configure(
    *, compile_btn_, compile_tooltip_, benchmark_endpoint_input_, benchmark_pipeline_id_input_,
    update_compile_button,
) -> None:
    """Store the compile button, its tooltip, the benchmark input widgets and the compile-button updater created by the UI."""
    global compile_btn, compile_tooltip, benchmark_endpoint_input, benchmark_pipeline_id_input
    global _update_compile_button
    compile_btn = compile_btn_
    compile_tooltip = compile_tooltip_
    benchmark_endpoint_input = benchmark_endpoint_input_
    benchmark_pipeline_id_input = benchmark_pipeline_id_input_
    _update_compile_button = update_compile_button


async def _fetch_models() -> dict:
    """Fetch the vision and VLM models known to the host server.

    Returns:
        dict: The server response plus `reachable: True`; on failure (or no URL) `{'vision_models': [], 'vlm_models': [], 'reachable': False}` with a warning notification.
    """
    if not HOST_SERVER_URL:
        return {'vision_models': [], 'vlm_models': [], 'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f'{HOST_SERVER_URL}/api/v1/models', headers={'X-API-Key': HOST_SERVER_API_KEY})
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except Exception as exc:
        ui.notify(f'Model discovery unavailable ({exc}) -- enter paths manually', type='warning')
        return {'vision_models': [], 'vlm_models': [], 'reachable': False}


async def _fetch_devices() -> dict:
    """Fetch the AI devices listed by the host server.

    Returns:
        dict: `{'devices': [...], 'reachable': bool}`; empty and unreachable on failure, with a warning notification.
    """
    if not HOST_SERVER_URL:
        return {'devices': [], 'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f'{HOST_SERVER_URL}/api/v1/devices', headers={'X-API-Key': HOST_SERVER_API_KEY})
            resp.raise_for_status()
            return {'devices': resp.json().get('devices', []), 'reachable': True}
    except Exception as exc:
        ui.notify(f'Device discovery unavailable ({exc}) -- enter device index manually', type='warning')
        return {'devices': [], 'reachable': False}


async def _fetch_model_meta_key(model_name: str) -> str | None:
    """Look up the default postprocess meta_key of a model on the host server.

    Args:
        model_name (str): Model catalog name.

    Returns:
        str | None: The meta_key, or None (with a notification) when it is unavailable.
    """
    if not HOST_SERVER_URL:
        ui.notify('Host server not configured -- enter meta_key manually', type='warning')
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/models/{model_name}/meta-key',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            if resp.status_code in (404, 409, 422):
                ui.notify(resp.json().get('detail', f'meta_key lookup failed (HTTP {resp.status_code})'),
                          type='warning', multi_line=True)
                return None
            resp.raise_for_status()
            return resp.json()['meta_key']
    except Exception as exc:
        ui.notify(f'meta_key lookup failed ({exc}) -- enter manually', type='warning')
        return None



async def _fetch_prebuilt_models() -> dict:
    """Fetch the prebuilt model catalog (axdownloadmodel) from the host server.

    Returns:
        dict: `{'models': [...], 'reachable': bool}`.
    """
    if not HOST_SERVER_URL:
        return {'models': [], 'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f'{HOST_SERVER_URL}/api/v1/prebuilt-models', headers={'X-API-Key': HOST_SERVER_API_KEY})
            resp.raise_for_status()
            return {'models': resp.json().get('models', []), 'reachable': True}
    except Exception as exc:
        ui.notify(f'Prebuilt model catalog unavailable ({exc}) -- enter model name manually', type='warning')
        return {'models': [], 'reachable': False}


async def _download_prebuilt_model(name: str, *, opencl: bool = True, device: Optional[int] = None,
                                    aipu_cores: int = CORES_PER_DEVICE, force: bool = False,
                                    artifacts_only: bool = False) -> dict:
    """Ask the host server to download and prepare a prebuilt model.

    Prints `[DEBUG ...]` trace lines to stdout. The request can take up to 30 minutes.

    Args:
        name (str): Prebuilt model name.
        opencl (bool, optional): Sent as `opencl`. Defaults to True.
        device (int | None, optional): Device index sent to the server.
        aipu_cores (int, optional): Sent as `aipu_cores`. Defaults to `CORES_PER_DEVICE`.
        force (bool, optional): Sent as `force`. Defaults to False.
        artifacts_only (bool, optional): Sent as `artifacts_only`. Defaults to False.

    Returns:
        dict: The server response plus `reachable: True`; `{'reachable': True, 'error': detail}` on an HTTP error; `{'reachable': False, ...}` when the server cannot be reached.
    """

    print(f'[DEBUG {time.time():.3f}] _download_prebuilt_model ENTER name={name!r} opencl={opencl} device={device} '
          f'aipu_cores={aipu_cores} force={force} artifacts_only={artifacts_only} '
          f'HOST_SERVER_URL={HOST_SERVER_URL!r}', flush=True)
    if not HOST_SERVER_URL:
        print(f'[DEBUG {time.time():.3f}] _download_prebuilt_model: HOST_SERVER_URL falsy, returning early', flush=True)
        return {'reachable': False}
    try:
        print(f'[DEBUG {time.time():.3f}] _download_prebuilt_model: about to POST', flush=True)
        async with httpx.AsyncClient(timeout=1800.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/prebuilt-models/download',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                json={'name': name, 'opencl': opencl, 'device': device,
                      'aipu_cores': aipu_cores, 'force': force,
                      'artifacts_only': artifacts_only},
            )
        print(f'[DEBUG {time.time():.3f}] _download_prebuilt_model: POST returned status={resp.status_code}', flush=True)
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'error': detail}
    except Exception as exc:
        print(f'[DEBUG {time.time():.3f}] _download_prebuilt_model: EXCEPTION {type(exc).__name__}: {exc}', flush=True)
        return {'reachable': False, 'error': str(exc)}


async def _patch_axnet_meta_key(name: str, meta_key: str) -> dict:
    """Ask the host server to patch the postprocess meta_key of a model's .axnet.

    Returns:
        dict: The server response plus `reachable: True`, or `reachable` with an `error` on failure.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/prebuilt-models/patch-meta-key',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                json={'name': name, 'meta_key': meta_key},
            )
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


async def _fetch_devices_health(model: Optional[str] = None, model_version: Optional[str] = None) -> dict:
    """Run the health check on all devices in one blocking request (up to an hour).

    Args:
        model (str | None, optional): Model used for the smoke test.
        model_version (str | None, optional): Model version.

    Returns:
        dict: The server response plus `reachable: True`; on failure empty `devices` with zero counts and `reachable: False`.
    """

    if not HOST_SERVER_URL:
        return {'devices': [], 'healthy_count': 0, 'total_count': 0, 'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=3600.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/health/all',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                params={k: v for k, v in {'model': model, 'model_version': model_version}.items() if v},
            )
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except Exception as exc:
        ui.notify(f'Device health check failed ({exc})', type='warning')
        return {'devices': [], 'healthy_count': 0, 'total_count': 0, 'reachable': False}


async def _check_device_health(index: int, model: Optional[str] = None) -> dict:
    """Run the health check on one device.

    Not called anywhere in the repository at present.

    Args:
        index (int): Device index.
        model (str | None, optional): Model used for the smoke test.

    Returns:
        dict: The server response plus `reachable`, or `reachable` with an `error`.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/health/{index}',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                params={'model': model} if model else {},
            )
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'devices': [], 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


async def _check_devices_health_batch(indices: list[int], device_to_model: dict[int, Optional[str]]) -> dict:
    """Run the health check on selected devices, optionally with a model per device.

    Args:
        indices (list[int]): Device indices to check.
        device_to_model (dict[int, str | None]): Model per device index; entries outside `indices` or without a model are ignored.

    Returns:
        dict: The server response plus `reachable: True`; `{'reachable': True, 'devices': [], 'error': ...}` on an HTTP error; `{'reachable': False, ...}` otherwise.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    models = {idx: model for idx, model in device_to_model.items() if idx in indices and model}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/health',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                json={'device_indices': indices, 'models': models},
            )
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'devices': [], 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


async def _start_devices_health_check(model: Optional[str] = None, model_version: Optional[str] = None) -> dict:
    """Start the background health check on all devices; progress is read with `_poll_devices_health_status`.

    Args:
        model (str | None, optional): Model used for the smoke test.
        model_version (str | None, optional): Model version.

    Returns:
        dict: The server response (including `total`) plus `reachable: True`, or `{'reachable': False}`.
    """

    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/health/all/start',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                params={k: v for k, v in {'model': model, 'model_version': model_version}.items() if v},
            )
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except Exception as exc:
        ui.notify(f'Starting device health check failed ({exc})', type='warning')
        return {'reachable': False}


async def _poll_devices_health_status() -> dict:
    """Read the progress of the background health check.

    Returns:
        dict: The server status (for example `done`, `completed`, `total`, `devices`, `error`) plus `reachable`.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/devices/health/status',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except Exception as exc:
        ui.notify(f'Checking device health progress failed ({exc})', type='warning')
        return {'reachable': False}


async def _run_devices_throughput_test(
    device_indices: list[int], seconds: int,
    model: Optional[str] = None, model_version: Optional[str] = None,
) -> dict:
    """Run a throughput test on the given devices for a number of seconds.

    Args:
        device_indices (list[int]): Devices to load.
        seconds (int): Test duration; the request timeout is this plus 90 s.
        model (str | None, optional): Model to run.
        model_version (str | None, optional): Model version.

    Returns:
        dict: The server response plus `reachable: True`, or `reachable` with an `error`.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=seconds + 90.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/throughput',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
                json={
                    'device_indices': device_indices, 'seconds': seconds,
                    'model': model, 'model_version': model_version,
                },
            )
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'devices': [], 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


async def _fetch_devices_numa_plan(indices: list[int], cores_per_device: int = CORES_PER_DEVICE) -> dict:
    """Fetch a CPU/NUMA pinning plan for the given devices.

    Args:
        indices (list[int]): Device indices.
        cores_per_device (int, optional): Cores per instance. Defaults to `CORES_PER_DEVICE`.

    Returns:
        dict: The server response plus `reachable: True`; `{'reachable': False}` with a warning notification on failure.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/devices/numa_plan',
                params={'indices': ','.join(str(i) for i in indices), 'cores_per_device': cores_per_device},
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get('detail', exc.response.text)
        except ValueError:
            detail = exc.response.text
        ui.notify(f'Fetching CPU/NUMA plan failed: {detail}', type='warning')
        return {'reachable': False}
    except Exception as exc:
        ui.notify(f'Fetching CPU/NUMA plan failed ({exc})', type='warning')
        return {'reachable': False}


async def _fetch_cpu_topology() -> dict:
    """Fetch the host CPU and NUMA topology.

    Returns:
        dict: The server response plus `reachable: True`; `{'reachable': False}` with a warning notification on failure.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/devices/cpu_topology',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get('detail', exc.response.text)
        except ValueError:
            detail = exc.response.text
        ui.notify(f'Fetching CPU topology failed: {detail}', type='warning')
        return {'reachable': False}
    except Exception as exc:
        ui.notify(f'Fetching CPU topology failed ({exc})', type='warning')
        return {'reachable': False}


async def _apply_meta_key_overrides(cfg: ServerConfig) -> None:
    """Patch the host server's .axnet files for every net with a `meta_key_override`.

    Args:
        cfg (ServerConfig): Loaded vision config.

    Raises:
        RuntimeError: If the host server is unreachable or rejects a patch.
    """
    for net_name, net in cfg.nets.items():
        if not net.meta_key_override:
            continue
        model_name = _axnet_catalog_name(net.axnet)
        result = await _patch_axnet_meta_key(model_name, net.meta_key_override)
        if not result.get('reachable', False):
            raise RuntimeError(
                f"Couldn't reach host server to apply meta_key_override={net.meta_key_override!r} "
                f"for net '{net_name}' ({result.get('error') or 'host server unreachable'})"
            )
        if result.get('error'):
            raise RuntimeError(
                f"Net '{net_name}' has meta_key_override={net.meta_key_override!r} set but the host "
                f"server couldn't apply it: {result['error']} -- compile/provision this model first"
            )


async def _compile_pipeline_locally(
    doc_id: str, kind: str, config_path: str,
) -> list[tuple[str, int, Path, Optional[str], Optional[int]]]:
    """Compile the generated config into pipeline specs on this machine.

    Args:
        doc_id (str): Document id; specs are written under `compiled_specs/<doc_id>`.
        kind (str): Pipeline kind; only 'vision' is supported.
        config_path (str): Path of the generated YAML.

    Returns:
        list[tuple]: Per spec `(pipeline_id, port, pipeline_json_path, taskset_cpus, membind)`.

    Raises:
        RuntimeError: If `kind` is not 'vision'.
    """

    if kind != 'vision':
        raise RuntimeError(
            f"local compile is not supported for pipeline kind {kind!r} "
            "(the legacy 'vlm' node's compiler was removed)"
        )
    output_dir = Path(COMPILED_SPECS_DIR) / doc_id
    cfg = load_vision_config(config_path)
    specs = PipelineCompiler(cfg, output_dir=output_dir).compile_all()
    return [(s.pipeline_id, s.port, Path(s.pipeline_json_path), s.taskset_cpus, s.membind) for s in specs]


async def _upload_pipeline_spec(doc_id: str, spec_path: Path) -> str:
    """Upload a compiled spec file to the host server.

    Returns:
        str: Path where the host server saved the spec.

    Raises:
        RuntimeError: If `HOST_SERVER_URL` is not configured.
        httpx.HTTPStatusError: On an HTTP error response.
    """
    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL is not configured on this GUI instance')
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f'{HOST_SERVER_URL}/api/v1/pipeline-spec',
            headers={'X-API-Key': HOST_SERVER_API_KEY},
            json={'pipeline_id': doc_id, 'filename': spec_path.name, 'spec_content': spec_path.read_text()},
        )
        resp.raise_for_status()
        return resp.json()['saved_path']


async def _launch_pipeline(
    pipeline_id: str, port: int, spec_path: str, taskset_cpus: Optional[str], membind: Optional[int],
) -> dict:
    """Launch one pipeline on the host server from an uploaded spec.

    Args:
        pipeline_id (str): Pipeline id.
        port (int): Port to serve on.
        spec_path (str): Spec path on the host server.
        taskset_cpus (str | None): CPU list to pin to.
        membind (int | None): NUMA node to bind memory to.

    Returns:
        dict: Server response.

    Raises:
        RuntimeError: If `HOST_SERVER_URL` is not configured.
        httpx.HTTPStatusError: On an HTTP error response.
    """
    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL is not configured on this GUI instance')
    async with httpx.AsyncClient(timeout=200.0) as client:
        resp = await client.post(
            f'{HOST_SERVER_URL}/api/v1/pipelines/launch',
            headers={'X-API-Key': HOST_SERVER_API_KEY},
            json={
                'pipeline_id': pipeline_id,
                'port': port,
                'spec_path': spec_path,
                'taskset_cpus': taskset_cpus,
                'membind': membind,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _shutdown_pipeline(pipeline_id: str) -> dict:
    """Shut down a pipeline on the host server.

    Raises:
        RuntimeError: If `HOST_SERVER_URL` is not configured.
        httpx.HTTPStatusError: On an HTTP error response.
    """
    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL is not configured on this GUI instance')
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f'{HOST_SERVER_URL}/api/v1/pipelines/shutdown',
            headers={'X-API-Key': HOST_SERVER_API_KEY},
            json={'pipeline_id': pipeline_id},
        )
        resp.raise_for_status()
        return resp.json()


async def _cleanup_all_pipelines() -> dict:
    """Ask the host server to clean up all pipelines.

    Returns:
        dict: Server response.

    Raises:
        RuntimeError: If `HOST_SERVER_URL` is not configured.
        httpx.HTTPStatusError: On an HTTP error response.
    """
    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL is not configured on this GUI instance')
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f'{HOST_SERVER_URL}/api/v1/pipelines/cleanup-all',
            headers={'X-API-Key': HOST_SERVER_API_KEY},
        )
        resp.raise_for_status()
        return resp.json()


async def _fetch_vllm_artifacts() -> dict:
    """Fetch the available vLLM artifact directories from the host server.

    Returns:
        dict: The server response plus `reachable: True`, or `{'artifacts': [], 'reachable': False}`.
    """
    if not HOST_SERVER_URL:
        return {'artifacts': [], 'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/vllm/artifacts', headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            resp.raise_for_status()
            return {**resp.json(), 'reachable': True}
    except httpx.HTTPError:
        return {'artifacts': [], 'reachable': False}


async def _launch_vllm_instance(name: str, data: dict, device: str, port: int) -> dict:
    """Launch one vLLM server on the host server.

    Args:
        name (str): Instance name.
        data (dict): Node data (`artifact`, `enable_thinking`, `temperature`).
        device (str): Device name to run on.
        port (int): Port to serve on.

    Returns:
        dict: Server response.

    Raises:
        RuntimeError: If `HOST_SERVER_URL` is not configured.
        httpx.HTTPStatusError: On an HTTP error response.
    """

    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL is not configured on this GUI instance')
    async with httpx.AsyncClient(timeout=200.0) as client:
        resp = await client.post(
            f'{HOST_SERVER_URL}/api/v1/vllm/launch',
            headers={'X-API-Key': HOST_SERVER_API_KEY},
            json={
                'name': name,
                'artifact': data.get('artifact'),
                'port': port,
                'device': device,
                'enable_thinking': bool(data.get('enable_thinking', False)),
                'temperature': float(data.get('temperature') or 0.0),
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _launch_vllm(node_id: str, data: dict) -> list[dict]:
    """Launch one vLLM server per device of a (V/L)LM node.

    Ports are `port`, `port + 1`, ... per device. The instance name is the node id for a single device, otherwise `<node_id>__<device>` with unsafe characters replaced by '-'.

    Args:
        node_id (str): Canvas node id.
        data (dict): Node data (`port`, `devices`, ...).

    Returns:
        list[dict]: One launch response per device, each with `name` and `device` added.
    """
    devices = _vllm_node_devices(data)
    base_port = int(data.get('port') or 8001)
    results = []
    for i, device in enumerate(devices):
        safe_device = re.sub(r'[^A-Za-z0-9_-]', '-', device)
        name = node_id if len(devices) == 1 else f'{node_id}__{safe_device}'
        result = await _launch_vllm_instance(name, data, device, base_port + i)
        result['name'] = name
        result['device'] = device
        results.append(result)
    return results


async def _render_detected_meta_key_field(
    data: dict, widgets: dict, field_key: str, *, label: str = 'Output meta key',
) -> None:
    """Render a read-only meta_key field with a refresh button that detects it from the selected model.

    Also fills the field immediately if the node has no value and the .axnet already has a default meta_key. The refresh button reads the .axnet and, if needed, asks the host server to generate it first (this prints `[DEBUG ...]` trace lines).

    Args:
        data (dict): Node data; the detected value is stored under `field_key`.
        widgets (dict): Widget registry; `axnet`, `device` and `cores` are read from it and the new field is stored under `field_key`.
        field_key (str): Key of the field in `data` and `widgets`.
        label (str, optional): Field label. Defaults to 'Output meta key'.
    """
    with ui.row().classes('w-full items-end gap-1 no-wrap'):
        widgets[field_key] = ui.input(label, value=data.get(field_key) or '') \
            .props('dense outlined readonly').classes('flex-grow')

        async def _on_refresh() -> None:
            """Detect the meta_key of the selected model and write it into the field."""
            print(f'[DEBUG {time.time():.3f}] _on_refresh ENTER', flush=True)
            axnet_widget = widgets.get('axnet')
            axnet_value = (axnet_widget.value if axnet_widget is not None else None) or data.get('axnet')
            model_name = _axnet_catalog_name(axnet_value or '')
            print(f'[DEBUG {time.time():.3f}] _on_refresh axnet_widget={axnet_widget!r} axnet_value={axnet_value!r} '
                  f'model_name={model_name!r}', flush=True)
            if not model_name:
                print(f'[DEBUG {time.time():.3f}] _on_refresh: no model_name, early return', flush=True)
                ui.notify('Pick a model first', type='warning')
                return
            meta_key = _read_axnet_default_meta_key(axnet_value)
            print(f'[DEBUG {time.time():.3f}] _on_refresh: local meta_key lookup -> {meta_key!r}', flush=True)
            if meta_key is None:
                spinner = ui.notification(
                    f'Generating .axnet for {model_name} (1-frame smoke test)...', spinner=True, timeout=None)
                device_widget, cores_widget = widgets.get('device'), widgets.get('cores')
                print(f'[DEBUG {time.time():.3f}] _on_refresh: device_widget={device_widget!r} cores_widget={cores_widget!r} '
                      f'device_widget.value={getattr(device_widget, "value", "<no .value>")!r} '
                      f'cores_widget.value={getattr(cores_widget, "value", "<no .value>")!r}', flush=True)
                try:
                    result = await _download_prebuilt_model(
                        model_name,
                        opencl=GLOBAL_SETTINGS['use_axinference_net_opencl'],
                        device=int(device_widget.value) if device_widget is not None else None,
                        aipu_cores=int(cores_widget.value) if cores_widget is not None else CORES_PER_DEVICE,
                    )
                except Exception as exc:
                    import traceback
                    print(f'[DEBUG {time.time():.3f}] _on_refresh: EXCEPTION before/during _download_prebuilt_model call: '
                          f'{type(exc).__name__}: {exc}', flush=True)
                    traceback.print_exc()
                    spinner.dismiss()
                    raise
                print(f'[DEBUG {time.time():.3f}] _on_refresh: _download_prebuilt_model returned {result!r}', flush=True)
                spinner.dismiss()
                if not result.get('reachable', False) or result.get('error'):
                    ui.notify(f"Could not determine meta_key for {model_name}: "
                              f"{result.get('error') or 'host server unreachable'}",
                              type='negative', multi_line=True, timeout=10000)
                    return
                meta_key = _read_axnet_default_meta_key(result['axnet_path'])
            if meta_key is None:
                ui.notify(f'.axnet for {model_name} has no postprocess meta_key', type='negative')
                return
            data[field_key] = meta_key
            widgets[field_key].value = meta_key
            print(f'[DEBUG {time.time():.3f}] _on_refresh: SUCCESS, meta_key={meta_key!r} set on '
                  f'widgets[{field_key!r}]', flush=True)
            ui.notify(f"{label} set to '{meta_key}'", type='positive')

        ui.button(icon='refresh', on_click=_on_refresh).props('dense flat round size=sm') \
            .tooltip('Detect from the compiled model (generates it first if needed)')

    if not data.get(field_key):
        axnet_widget = widgets.get('axnet')
        axnet_value = (axnet_widget.value if axnet_widget is not None else None) or data.get('axnet')
        meta_key = _read_axnet_default_meta_key(axnet_value or '')
        if meta_key:
            data[field_key] = meta_key
            widgets[field_key].value = meta_key
async def _on_compile_clicked() -> None:
    """Compile the generated config and launch the pipelines on the host server.

    Steps: launch connected (V/L)LM nodes (after a device health check, skipping unhealthy devices); compile the generated YAML; shut down earlier instances of the same pipeline ids; provision every referenced prebuilt model and recompile with the resolved paths; apply meta_key overrides; check device health; upload the specs; launch the pipelines; point the Benchmarking inputs at the new endpoints. Failures are reported as notifications and stop the flow. Only one run is allowed at a time (`core.app.state.compile_in_progress`); the compile button is refreshed when it ends.
    """

    doc_id = _last_generated['doc_id']
    kind = _last_generated['kind']
    config_path = _last_generated['out_path']
    vllm_nodes = _connected_vllm_nodes()
    if doc_id is None and not vllm_nodes:
        ui.notify('Generate a config YAML first', type='warning')
        return
    if core.app.state.compile_in_progress:
        ui.notify('Compile/launch already in progress -- please wait', type='warning')
        return

    core.app.state.compile_in_progress = True
    compile_btn.disable()
    compile_tooltip.text = 'Compile/launch already in progress -- please wait for it to finish'
    try:
        if vllm_nodes:
            vllm_device_names = sorted({
                name for node in vllm_nodes for name in (node.get('data', {}).get('devices') or [])
            })
            name_to_index: dict = {}
            if vllm_device_names:
                devices_result = await _fetch_devices()
                name_to_index = {
                    d['name']: d['index'] for d in devices_result.get('devices', [])
                    if d['name'] in vllm_device_names
                }
                indices = sorted(name_to_index.values())
                if indices:
                    health_notif = ui.notification(
                        'Checking (V/L)LM device health before launching...', spinner=True, timeout=None,
                    )
                    result = await _check_devices_health_batch(indices, {})
                    health_notif.dismiss()
                    if result.get('reachable', False) and not (result.get('error') and not result.get('devices')):
                        by_index = {d['index']: d for d in result.get('devices', [])}
                        for idx in indices:
                            device_result = by_index.get(idx)
                            if device_result is None or not device_result.get('healthy', False):
                                _unhealthy_devices.add(idx)
                            else:
                                _unhealthy_devices.discard(idx)

            vllm_notif = ui.notification(
                f'Launching {len(vllm_nodes)} vLLM VLM server(s)...', spinner=True, timeout=None,
            )
            vllm_launched: list[tuple[str, int]] = []
            vllm_failed: list[tuple[str, str]] = []
            for node in vllm_nodes:
                node_id = node['id']
                data = node.get('data', {})
                bad_devices = [
                    dev for dev in (data.get('devices') or [])
                    if name_to_index.get(dev) in _unhealthy_devices
                ]
                if bad_devices:
                    vllm_failed.append((
                        node_id,
                        f"device(s) {', '.join(bad_devices)} failed a health check -- "
                        "pick a different device in this node's dialog",
                    ))
                    continue
                try:
                    results = await _launch_vllm(node_id, data)
                    vllm_launched.extend((r['name'], r['port']) for r in results)
                except Exception as exc:
                    vllm_failed.append((node_id, str(exc)))
            vllm_notif.dismiss()
            if vllm_launched:
                summary = ', '.join(f'{node_id} (port {port})' for node_id, port in vllm_launched)
                ui.notify(f'Launched {len(vllm_launched)} vLLM VLM server(s): {summary}',
                          type='positive', multi_line=True, timeout=8000)
            if vllm_failed:
                summary = '; '.join(f'{node_id}: {err}' for node_id, err in vllm_failed)
                ui.notify(f'vLLM launch failed for {len(vllm_failed)} node(s): {summary}',
                          type='negative', multi_line=True, timeout=12000)
            if vllm_launched:
                await _chat_refresh_groups()

        skipped_vllm = [
            n['id'] for n in current_graph['nodes']
            if n.get('data', {}).get('kind') == 'vllm_vlm' and not _predecessors(n['id'])
        ]
        if skipped_vllm:
            ui.notify(
                f"Skipped {len(skipped_vllm)} (V/L)LM node(s) not yet connected to anything: "
                f"{', '.join(skipped_vllm)}",
                type='warning', multi_line=True, timeout=8000,
            )

        if doc_id is None:
            return

        compile_notif = ui.notification('Compiling...', spinner=True, timeout=None)
        try:
            specs = await _compile_pipeline_locally(doc_id, kind, config_path)
        except Exception as exc:
            compile_notif.dismiss()
            ui.notify(f'Compile failed: {exc}', type='negative', multi_line=True, timeout=8000)
            return
        compile_notif.dismiss()

        if kind == 'vision':
            for spec_pipeline_id, _port, _spec_path, _taskset_cpus, _membind in specs:
                try:
                    await _shutdown_pipeline(spec_pipeline_id)
                except Exception:
                    pass

        device_to_model = {
            dev: n['data'].get('axnet')
            for n in current_graph['nodes']
            if n.get('data', {}).get('kind') == 'vision'
            for dev in _node_device_indices(n['data'])
        }
        device_indices = sorted({
            dev for n in current_graph['nodes']
            if n.get('data', {}).get('kind') == 'vision'
            for dev in _node_device_indices(n['data'])
        })
        if device_indices:
            try:
                cfg_doc = yaml.safe_load(Path(config_path).read_text()) or {}
            except Exception as exc:
                cfg_doc = {}
                ui.notify(f'Could not read generated config to sanity-check models: {exc}', type='warning')
            global_section = cfg_doc.get('global') or {}
            opencl = global_section.get('use_axinference_net_opencl', '--enable-opencl') == '--enable-opencl'
            nets = cfg_doc.get('nets') or {}
            prebuilt_nets = [
                (net_key, _axnet_catalog_name(net['axnet']), int(net.get('cores') or CORES_PER_DEVICE))
                for net_key, net in nets.items()
                if isinstance(net, dict) and net.get('axnet')
            ]
            if prebuilt_nets:
                unique_combos: dict[tuple[str, int], list[str]] = {}
                for net_key, model_name, cores in prebuilt_nets:
                    unique_combos.setdefault((model_name, cores), []).append(net_key)
                provision_notif = ui.notification(
                    f'Provisioning {len(unique_combos)} unique model(s) '
                    f'({len(prebuilt_nets)} pipeline net(s) reference them)...',
                    spinner=True, timeout=None,
                )
                provision_failed = []
                sanity_device = device_indices[0]
                for (model_name, cores), net_keys in unique_combos.items():
                    result = await _download_prebuilt_model(
                        model_name, opencl=opencl, device=sanity_device, aipu_cores=cores, force=True,
                    )
                    if not result.get('reachable', False):
                        provision_failed.extend((net_key, model_name, 'could not reach host server') for net_key in net_keys)
                    elif result.get('error'):
                        provision_failed.extend((net_key, model_name, result['error']) for net_key in net_keys)
                provision_notif.dismiss()
                if provision_failed:
                    summary = '; '.join(f'{net_key} ({model_name}): {err}' for net_key, model_name, err in provision_failed)
                    ui.notify(f'Cannot compile -- model provisioning failed: {summary}',
                              type='negative', multi_line=True, timeout=12000)
                    return

                for net_key, model_name, _cores in prebuilt_nets:
                    nets[net_key]['axnet'] = f'${{SDK_ROOT}}/build/{model_name}/{model_name}.axnet'
                try:
                    Path(config_path).write_text(yaml.safe_dump(cfg_doc, sort_keys=False, default_flow_style=False))
                    specs = await _compile_pipeline_locally(doc_id, kind, config_path)
                except Exception as exc:
                    ui.notify(f'Could not recompile after resolving provisioned model paths: {exc}',
                              type='negative', multi_line=True, timeout=10000)
                    return

                if kind == 'vision':
                    try:
                        patch_cfg = load_vision_config(config_path)
                        await _apply_meta_key_overrides(patch_cfg)
                    except Exception as exc:
                        ui.notify(f'Could not apply meta_key_override after provisioning: {exc}',
                                  type='negative', multi_line=True, timeout=10000)
                        return

            health_notif = ui.notification('Checking device health before compiling...', spinner=True, timeout=None)
            failed = []
            result = await _check_devices_health_batch(device_indices, device_to_model)
            if not result.get('reachable', False):
                pass
            elif result.get('error') and not result.get('devices'):
                ui.notify(f'Device health check unavailable ({result["error"]}) -- skipping pre-compile check',
                          type='warning')
            else:
                by_index = {d['index']: d for d in result.get('devices', [])}
                for idx in device_indices:
                    device_result = by_index.get(idx)
                    if device_result is None or not device_result.get('healthy', False):
                        failed.append((idx, (device_result or {}).get('error') or 'unknown error'))
                        _unhealthy_devices.add(idx)
                    else:
                        _unhealthy_devices.discard(idx)
            health_notif.dismiss()
            if failed:
                summary = '; '.join(f'device {idx}: {err}' for idx, err in failed)
                ui.notify(f'Cannot compile -- faulty device(s) detected: {summary}',
                          type='negative', multi_line=True, timeout=10000)
                return

        upload_notif = ui.notification('Uploading compiled spec(s)...', spinner=True, timeout=None)
        try:
            uploaded = []
            for spec_pipeline_id, port, spec_path, taskset_cpus, membind in specs:
                saved_path = await _upload_pipeline_spec(doc_id, spec_path)
                uploaded.append((spec_pipeline_id, port, saved_path, taskset_cpus, membind))
        except Exception as exc:
            upload_notif.dismiss()
            ui.notify(f'Upload failed: {exc}', type='negative', multi_line=True, timeout=8000)
            return
        upload_notif.dismiss()

        summary = '\n'.join(
            f'{spec_pipeline_id} (port {port}): {saved_path}' for spec_pipeline_id, port, saved_path, _, _ in uploaded
        )
        ui.notify(f'Compiled {len(uploaded)} pipeline spec(s) and sent to the host server:\n{summary}',
                  type='positive', multi_line=True, timeout=10000)

        endpoint_host = (urlparse(HOST_SERVER_URL).hostname if HOST_SERVER_URL else None) or 'localhost'

        launch_notif = ui.notification('Launching pipeline(s)...', spinner=True, timeout=None)
        launched: list[tuple[str, int]] = []
        launch_failed: list[tuple[str, str]] = []
        for spec_pipeline_id, port, saved_path, taskset_cpus, membind in uploaded:
            try:
                await _launch_pipeline(spec_pipeline_id, port, saved_path, taskset_cpus, membind)
                launched.append((spec_pipeline_id, port))
            except Exception as exc:
                launch_failed.append((spec_pipeline_id, str(exc)))
        launch_notif.dismiss()

        if launch_failed:
            summary = '; '.join(f'{pid}: {err}' for pid, err in launch_failed)
            ui.notify(f'Launch failed for {len(launch_failed)} pipeline(s): {summary}',
                      type='negative', multi_line=True, timeout=12000)
        if not launched:
            return
        ui.notify(f'Launched {len(launched)} pipeline(s)', type='positive', timeout=6000)

        endpoints = ', '.join(f'{endpoint_host}:{port}' for _, port in launched)
        benchmark_endpoint_input.set_value(endpoints)
        _on_benchmark_endpoints_changed(endpoints)
        pipeline_ids = ', '.join(pid for pid, _ in launched)
        benchmark_pipeline_id_input.set_value(pipeline_ids)
        _on_benchmark_pipeline_ids_changed(pipeline_ids)
    finally:
        core.app.state.compile_in_progress = False
        _update_compile_button()
