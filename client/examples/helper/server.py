"""Thin client for the host server REST API used by the helper CLI.

Exposes the exit codes, the ServerError and UsageError exceptions, and one function per server operation (devices, models, power, NUMA pinning, media, vLLM).

Note:
    Needs HOST_SERVER_URL and HOST_SERVER_API_KEY in the environment.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


class ServerError(RuntimeError):
    """The server was unreachable or answered with an error."""
    pass


class UsageError(RuntimeError):
    """The caller supplied invalid input or the environment is not set up."""
    pass


def log(msg: str) -> None:
    """Print a timestamped progress message to stderr."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', file=sys.stderr, flush=True)


def require_env() -> tuple[str, str]:
    """Read the server URL and API key from the environment.

    Returns:
        tuple[str, str]: (HOST_SERVER_URL without a trailing slash, HOST_SERVER_API_KEY).

    Raises:
        UsageError: If either variable is unset or empty.
    """
    url, key = os.environ.get('HOST_SERVER_URL', '').rstrip('/'), os.environ.get('HOST_SERVER_API_KEY', '')
    if not url or not key:
        raise UsageError('HOST_SERVER_URL and HOST_SERVER_API_KEY must be set (see the README)')
    return url, key


def api(method: str, path: str, timeout: float = 30.0, **kwargs) -> httpx.Response:
    """Call an /api/v1 endpoint with the API key.

    Args:
        method (str): HTTP method.
        path (str): Path below /api/v1, starting with `/`.
        timeout (float, optional): Request timeout in seconds. Defaults to 30.0.
        **kwargs: Passed to httpx.request (json, params, ...).

    Returns:
        httpx.Response: The response, always status 200.

    Raises:
        ServerError: On a transport error or any non-200 status.
    """
    url, key = require_env()
    try:
        r = httpx.request(method, f'{url}/api/v1{path}', headers={'X-API-Key': key}, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        raise ServerError(f'{method} {path}: {exc}') from exc
    if r.status_code != 200:
        try:
            detail = r.json().get('detail', r.text)
        except ValueError:
            detail = r.text
        raise ServerError(f'{method} {path}: HTTP {r.status_code}: {str(detail)[:400]}')
    return r


def check_health() -> dict:
    """Query the unauthenticated health endpoint.

    Returns:
        dict: The parsed JSON reply.

    Raises:
        UsageError: If HOST_SERVER_URL is unset.
        ServerError: If the request fails.
    """
    url = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
    if not url:
        raise UsageError('HOST_SERVER_URL must be set (see the README)')
    try:
        r = httpx.get(f'{url}/api/v1/health', timeout=10.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServerError(f'GET /health: {exc}') from exc
    return r.json()


def device_indexes() -> list[int]:
    """Return the sorted indexes of the devices the server reports."""
    return sorted(d['index'] for d in api('GET', '/devices').json().get('devices', []))


def device_health(indexes: list[int], timeout: float = 900.0) -> list[dict]:
    """Health-check devices on the server.

    Args:
        indexes (list[int]): Device indexes to check.
        timeout (float, optional): Request timeout in seconds. Defaults to 900.0.

    Returns:
        list[dict]: One report per device with at least `index`, `name` and `healthy`.
    """
    return api('POST', '/devices/health', timeout=timeout, json={'device_indices': indexes}).json()['devices']


def healthy_devices(spec: str = 'auto', num_devices: int = 1) -> list[int]:
    """Health-check devices and return the usable ones.

    Logs one line per device checked.

    Args:
        spec (str, optional): 'auto' for every device the server has, or a comma-separated list of indexes. Defaults to 'auto'.
        num_devices (int, optional): With 'auto', how many healthy devices to return. Defaults to 1.

    Returns:
        list[int]: With 'auto', the first `num_devices` healthy indexes; otherwise exactly the requested ones.

    Raises:
        UsageError: If a requested device is not present.
        ServerError: If there are no devices, too few healthy ones, or a requested device is unhealthy.
    """
    present = device_indexes()
    if not present:
        raise ServerError('the server reports no devices')
    wanted = present if spec == 'auto' else [int(x) for x in spec.split(',')]
    missing = [d for d in wanted if d not in present]
    if missing:
        raise UsageError(f'device(s) {missing} not present; the server has {present}')
    report = device_health(wanted)
    healthy = [d['index'] for d in report if d['healthy']]
    for d in report:
        log(f'device {d["index"]} ({d["name"]}): ' + ('healthy' if d['healthy'] else f'UNHEALTHY: {str(d.get("error"))[:100]}'))
    if spec == 'auto':
        if len(healthy) < num_devices:
            raise ServerError(f'asked for {num_devices} healthy device(s), only {healthy} are healthy')
        return healthy[:num_devices]
    unhealthy = [d for d in wanted if d not in healthy]
    if unhealthy:
        raise ServerError(f'device(s) {unhealthy} unhealthy; healthy devices: {healthy} (or use --devices auto)')
    return wanted


def select_first_healthy(preferred: int = 0) -> int:
    """Find the first healthy device, trying `preferred` first, then the others in index order.

    Args:
        preferred (int, optional): Index tried first when present. Defaults to 0.

    Returns:
        int: The device index.

    Raises:
        ServerError: If no device is healthy.
    """
    present = device_indexes()
    order = ([preferred] if preferred in present else []) + [i for i in present if i != preferred]
    failures = []
    for idx in order:
        dev = device_health([idx])[0]
        if dev['healthy']:
            log(f'device {idx} ({dev["name"]}) is healthy')
            return idx
        failures.append(f'device {idx} ({dev["name"]}): {str(dev.get("error"))[:100]}')
        log(f'device {idx} is unhealthy, trying the next: {failures[-1]}')
    raise ServerError(f'no healthy device among {order}: ' + '; '.join(failures))


def stop_all() -> dict:
    """Stop every pipeline and vLLM server on the host.

    Returns:
        dict: The server's reply, including `killed_pids` and `killed_vllm_names`.
    """
    return api('POST', '/pipelines/cleanup-all', timeout=120.0).json()


def list_models() -> dict:
    """List the models known to the server.

    Returns:
        dict: Lists of names under `prebuilt`, `vision_built`, `vlm_built` and `vllm_artifacts`.
    """
    return {
        'prebuilt': api('GET', '/prebuilt-models').json().get('models', []),
        'vision_built': [m['name'] for m in api('GET', '/models').json().get('vision_models', [])],
        'vlm_built': [m['name'] for m in api('GET', '/models').json().get('vlm_models', [])],
        'vllm_artifacts': [a['name'] for a in api('GET', '/vllm/artifacts').json().get('artifacts', [])],
    }


def provision_model(name: str, device: int, meta_key: str | None = None) -> str:
    """Download and compile a prebuilt model, optionally patching its meta_key.

    Can take several minutes the first time. Compiles for 3 AIPU cores without OpenCL.

    Args:
        name (str): Prebuilt model name.
        device (int): Device to compile on.
        meta_key (str | None, optional): Postprocess meta_key to patch into the .axnet. Defaults to None.

    Returns:
        str: The axnet path reported by the server, or '' if none.
    """
    body = {'name': name, 'opencl': False, 'device': device, 'aipu_cores': 3, 'force': False, 'artifacts_only': False}
    log(f'provisioning {name} on device {device} (can take several minutes the first time)')
    res = api('POST', '/prebuilt-models/download', timeout=3600.0, json=body).json()
    log(f'{name}: {"already present" if res.get("already_present") else "downloaded"}, axnet {res.get("axnet_path")}')
    if meta_key:
        patched = api('POST', '/prebuilt-models/patch-meta-key', json={'name': name, 'meta_key': meta_key}).json()
        log(f'{name}: meta_key {meta_key!r} patched={patched.get("patched")}')
    return res.get('axnet_path', '')


def axdevice_status(device: int) -> dict:
    """Return the axdevice status of a device, including its power limit."""
    return api('GET', f'/devices/{device}/axdevice', timeout=60.0).json()


def set_power_limit(device: int, limit: str) -> dict:
    """Set or clear the power limit of a device.

    Args:
        device (int): Device index.
        limit (str): Watts as a number, or 'off'.

    Returns:
        dict: The server's reply with the power limit before and after and the axdevice steps run.

    Raises:
        UsageError: If `limit` is neither a number nor 'off'.
    """
    try:
        value: float | str = 'off' if limit == 'off' else float(limit)
    except ValueError:
        raise UsageError(f"--limit must be watts or 'off', got {limit!r}") from None
    return api('POST', f'/devices/{device}/axdevice', timeout=120.0, json={'power_limit_w': value, 'confirm': True}).json()


def cpu_topology() -> dict:
    """Return the host CPU and NUMA topology."""
    return api('GET', '/devices/cpu_topology').json()


def numa_plan(devices: list[int], cores_per_device: int = 4) -> dict:
    """Get the server's CPU plan for a set of devices.

    Args:
        devices (list[int]): Device indexes.
        cores_per_device (int, optional): CPU cores to reserve per device. Defaults to 4.

    Returns:
        dict: The reply with a `plan` entry per device and `numa_available`.
    """
    return api('GET', '/devices/numa_plan', params={'indices': ','.join(str(d) for d in devices),
                                                    'cores_per_device': cores_per_device}).json()


def merge_cpu_ranges(cpus: list[int]) -> str:
    """Collapse CPU ids into a taskset-style range string.

    Example:
        [0, 1, 2, 5] becomes '0-2,5'.

    Args:
        cpus (list[int]): CPU ids, in any order, duplicates allowed.

    Returns:
        str: Comma-separated ranges.
    """
    merged: list[list[int]] = []
    for cpu in sorted(set(cpus)):
        if merged and cpu <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], cpu)
        else:
            merged.append([cpu, cpu])
    return ','.join(f'{lo}-{hi}' if hi != lo else str(lo) for lo, hi in merged)


def pin_groups(groups: list[list[int]], cores_per_device: int = 4) -> list[dict]:
    """Plan CPU pinning for groups of devices.

    Args:
        groups (list[list[int]]): Device indexes per pipeline.
        cores_per_device (int, optional): CPU cores reserved per device. Defaults to 4.

    Returns:
        list[dict]: One entry per group with `taskset_cpus` (range string) and `membind` (the NUMA node of the group's first device, or None when NUMA is unavailable).
    """

    flat = [d for g in groups for d in g]
    plan = numa_plan(flat, cores_per_device)
    by_device = {p['index']: p for p in plan['plan']}
    out = []
    for g in groups:
        cpus = [c for d in g for c in by_device[d]['cpus']]
        out.append({'taskset_cpus': merge_cpu_ranges(cpus),
                    'membind': by_device[g[0]]['numa_node'] if plan['numa_available'] else None})
    return out


def fetch_media(poll_s: float = 5.0, timeout_s: float = 3600.0) -> list[dict]:
    """Download the sample videos on the server and wait until it is done.

    An already running fetch (HTTP 409) is joined rather than restarted.

    Args:
        poll_s (float, optional): Seconds between status polls. Defaults to 5.0.
        timeout_s (float, optional): Give up after this many seconds. Defaults to 3600.0.

    Returns:
        list[dict]: One result per file with `file`, `status` and `detail`.

    Raises:
        ServerError: If the fetch does not finish in time.
    """

    try:
        api('POST', '/benchmark-media/fetch')
    except ServerError as exc:
        if 'HTTP 409' not in str(exc):
            raise
    deadline = time.monotonic() + timeout_s
    while True:
        st = api('GET', '/benchmark-media/status').json()
        if not st['running'] and st['ok'] is not None:
            return st['results']
        if time.monotonic() > deadline:
            raise ServerError('benchmark media fetch did not finish in time')
        log(f'fetching media: {st.get("current_file")} ({st.get("stage")}), {len(st["results"])}/{st["total"]} done')
        time.sleep(poll_s)


def device_name(index: int) -> str:
    """Look up the name of a device.

    Raises:
        UsageError: If the device is not present.
    """
    for d in api('GET', '/devices').json().get('devices', []):
        if d['index'] == index:
            return d['name']
    raise UsageError(f'device {index} not present')


def vllm_up(name: str, artifact: str, port: int, device: int, thinking: bool, temperature: float) -> dict:
    """Launch a vLLM server for a compiled artifact.

    Args:
        name (str): Instance name.
        artifact (str): Artifact name below ${SDK_ROOT}/build.
        port (int): Port to serve on.
        device (int): Device index; its name is sent to the server.
        thinking (bool): Enable chat-template thinking mode.
        temperature (float): Sampling temperature.

    Returns:
        dict: The server's reply, including `pid`, `port` and `context_length`.
    """
    body = {'name': name, 'artifact': f'${{SDK_ROOT}}/build/{artifact}/axscript', 'port': port,
            'device': device_name(device), 'enable_thinking': thinking, 'temperature': temperature}
    return api('POST', '/vllm/launch', timeout=240.0, json=body).json()


def vllm_status() -> list[dict]:
    """Return the vLLM instances the server knows about."""
    return api('GET', '/vllm/status').json()['instances']


def vllm_down(name: str) -> bool:
    """Stop a vLLM instance.

    Returns:
        bool: True if it was running and has been stopped.
    """
    return api('POST', '/vllm/shutdown', timeout=60.0, json={'name': name}).json()['stopped']
