"""Prepare the host server before a release test: clean up pipelines, pick a healthy device, raise its power limit and provision models.

Exposes prepare_host() plus the individual steps. Every step is skipped when HOST_SERVER_URL is unset.

Note:
    Environment: HOST_SERVER_URL, HOST_SERVER_API_KEY (sent as X-API-Key), DIRECT_TEST_DEVICE (preferred device index, default 0;
    overwritten with the selected device by select_device_and_power).
"""

import os
import time

import httpx

HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')

_PROVISION_OPENCL = False
_PROVISION_AIPU_CORES = 3
_MAX_DEVICE_ATTEMPTS = 4


def _headers():
    """Return the HTTP headers carrying the host server API key."""
    return {'X-API-Key': HOST_SERVER_API_KEY}


def cleanup_all_pipelines(set_power: bool = True) -> None:
    """Stop every running pipeline and vLLM server on the host server, then optionally raise the power limit.

    Failures are printed as warnings and do not raise. Sleeps 3 s after a successful cleanup.

    Args:
        set_power (bool, optional): Call set_max_power_limit() after a successful cleanup. Defaults to True.
    """

    if not HOST_SERVER_URL:
        print('WARNING: HOST_SERVER_URL not set -- skipping the pre-test pipeline cleanup')
        return
    try:
        resp = httpx.post(f'{HOST_SERVER_URL}/api/v1/pipelines/cleanup-all', headers=_headers(), timeout=60.0)
        resp.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        print(f'WARNING: pre-test pipeline cleanup failed: {exc}')
        return
    body = resp.json()
    print(f'PASS: pre-test cleanup -- stopped pids={body.get("killed_pids")} vllm={body.get("killed_vllm_names")}')
    time.sleep(3)
    if set_power:
        set_max_power_limit()


MAX_POWER_LIMIT_W = 100.0


def set_max_power_limit(first: int | None = None) -> None:
    """Raise the power limit of each device to MAX_POWER_LIMIT_W through the axdevice endpoint.

    Devices already at or above the limit (or reporting 'off') are left alone. Per-device failures are printed and skipped.

    Args:
        first (int | None, optional): Device index to handle before the others. Defaults to None.
    """

    if not HOST_SERVER_URL:
        return
    indexes = _device_indexes()
    if first is not None and first in indexes:
        indexes.remove(first)
        indexes.insert(0, first)
    for idx in indexes:
        url = f'{HOST_SERVER_URL}/api/v1/devices/{idx}/axdevice'
        try:
            before = httpx.get(url, headers=_headers(), timeout=60.0).json().get('power_limit_w')
            if before == 'off' or (isinstance(before, (int, float)) and before >= MAX_POWER_LIMIT_W):
                print(f'power limit: device {idx} already at {before} W')
                continue
            resp = httpx.post(url, headers=_headers(), timeout=120.0,
                              json={'power_limit_w': MAX_POWER_LIMIT_W, 'confirm': True})
            body = resp.json() if resp.status_code == 200 else {}
            if resp.status_code == 200 and body.get('ok'):
                print(f'PASS: power limit: device {idx} {before} W -> {body.get("power_limit_w_after")} W')
            else:
                detail = (body.get('steps') or [{}])[-1].get('stderr') or resp.text
                print(f'power limit: device {idx} not changed (was {before} W; the device may not support it): '
                      f'{str(detail)[:160]}')
        except (httpx.HTTPError, OSError, ValueError) as exc:
            print(f'power limit: device {idx} skipped: {exc}')


def _device_indexes() -> list[int]:
    """Return the sorted device indexes reported by the host server, or an empty list on any error."""
    try:
        resp = httpx.get(f'{HOST_SERVER_URL}/api/v1/devices', headers=_headers(), timeout=30.0)
        resp.raise_for_status()
        return sorted(d['index'] for d in resp.json().get('devices', []))
    except (httpx.HTTPError, OSError, ValueError, KeyError):
        return []


def _provision(name: str, device: int):
    """POST a prebuilt-model download request for one model on one device and return the raw response."""
    return httpx.post(
        f'{HOST_SERVER_URL}/api/v1/prebuilt-models/download',
        headers=_headers(),
        json={'name': name, 'opencl': _PROVISION_OPENCL, 'device': device, 'aipu_cores': _PROVISION_AIPU_CORES,
              'force': False, 'artifacts_only': False},
        timeout=1800.0,
    )


def ensure_prebuilt_models(names) -> None:
    """Make sure each named prebuilt model is built on the host server, trying several devices.

    Args:
        names (Iterable[str]): Prebuilt model names.

    Raises:
        RuntimeError: If a model could not be provisioned on any of the first _MAX_DEVICE_ATTEMPTS devices.
    """

    if not HOST_SERVER_URL:
        print('WARNING: HOST_SERVER_URL not set -- skipping the pre-test model provisioning')
        return
    devices = _device_indexes() or [0]
    for name in names:
        print(f'ensuring prebuilt model {name!r} is built on the host server')
        last_detail = ''
        for device in devices[:_MAX_DEVICE_ATTEMPTS]:
            try:
                resp = _provision(name, device)
            except (httpx.HTTPError, OSError) as exc:
                last_detail = f'device {device}: {exc}'
                continue
            if resp.status_code == 200:
                result = resp.json()
                print(f'PASS: prebuilt model {name!r} ready -- axnet_path={result.get("axnet_path")!r} '
                      f'already_present={result.get("already_present")} regenerated={result.get("regenerated")} '
                      f'(device {device})')
                break
            try:
                detail = resp.json().get('detail', resp.text)
            except ValueError:
                detail = resp.text
            last_detail = f'device {device}: HTTP {resp.status_code}: {str(detail)[:300]}'
            print(f'WARNING: provisioning {name!r} failed on {last_detail}; trying the next device')
        else:
            raise RuntimeError(f'failed to provision prebuilt model {name!r} on any of '
                               f'{devices[:_MAX_DEVICE_ATTEMPTS]}: {last_detail}')


def _vllm_artifact_names() -> set[str]:
    """Return the names of the vLLM artifacts deployed on the host server."""
    resp = httpx.get(f'{HOST_SERVER_URL}/api/v1/vllm/artifacts', headers=_headers(), timeout=30.0)
    resp.raise_for_status()
    return {a['name'] for a in resp.json().get('artifacts', [])}


def require_vllm_artifacts(test_name: str, names) -> bool:
    """Check that the named vLLM artifacts are deployed, recording a warning with deployment steps if not.

    An unreachable check is reported and treated as missing artifacts. With HOST_SERVER_URL unset the check is skipped.

    Args:
        test_name (str): Test name used in the SKIP line.
        names (Iterable[str]): Artifact names that must be deployed.

    Returns:
        bool: True if the check passed or was skipped, False if any artifact is missing.
    """
    from utils.release_gate import warn
    if not HOST_SERVER_URL:
        print('WARNING: HOST_SERVER_URL not set -- skipping the vLLM artifact check')
        return True
    names = list(names)
    missing = names
    try:
        deployed = _vllm_artifact_names()
        missing = [n for n in names if n not in deployed]
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f'WARNING: vLLM artifact check failed: {exc}')
    if not missing:
        print(f'PASS: vLLM artifact(s) {names} deployed on the host server')
        return True
    steps = '; '.join(f'put its weights in server/models/{n}/axscript (bash server/models/{n}.link pulls them, '
                      f'needs AWS credentials)' for n in missing)
    warn(f'vLLM artifact(s) not deployed on the host server: {missing}. {steps}; then deploy them with '
         f'server/models/deploy_to_sdk.sh --sdk-dir $SDK_ROOT --model <name> inside the server container '
         f'(server/QUICKSTART.md, "Deploy model artifacts"), and rerun')
    print(f'{test_name}: SKIP (artifacts not deployed: {missing})')
    return False


_selected_device: dict = {}


def select_healthy_device() -> int | None:
    """Find the first device whose health check passes and remember it.

    Tries DIRECT_TEST_DEVICE first (default 0), then the remaining devices in index order.

    Returns:
        int | None: The selected device index, or None when HOST_SERVER_URL is unset.

    Raises:
        SystemExit: With code 1 if no devices are reported or none is healthy.
    """

    if not HOST_SERVER_URL:
        return None
    indexes = _device_indexes()
    if not indexes:
        print('FAIL: no devices reported by GET /api/v1/devices -- nothing to run the test on')
        raise SystemExit(1)
    preferred = int(os.environ.get('DIRECT_TEST_DEVICE', '0'))
    order = ([preferred] if preferred in indexes else []) + [i for i in indexes if i != preferred]
    failures = []
    for idx in order:
        try:
            resp = httpx.post(f'{HOST_SERVER_URL}/api/v1/devices/health', headers=_headers(), timeout=300.0,
                              json={'device_indices': [idx]})
            resp.raise_for_status()
            dev = resp.json()['devices'][0]
        except (httpx.HTTPError, OSError, ValueError, KeyError, IndexError) as exc:
            failures.append(f'device {idx}: health check failed to run: {exc}')
            print(f'WARNING: {failures[-1]}')
            continue
        if dev.get('healthy'):
            _selected_device['index'], _selected_device['name'] = idx, dev.get('name')
            print(f'PASS: device {idx} ({dev.get("name")}) is healthy -- the test runs on it'
                  + (f' (devices {order[:order.index(idx)]} were unhealthy)' if idx != order[0] else ''))
            return idx
        failures.append(f'device {idx} ({dev.get("name")}): {str(dev.get("error"))[:120]}')
        print(f'WARNING: device {idx} is unhealthy, trying the next: {failures[-1]}')
    print(f'FAIL: no healthy device found among {len(order)} device(s): {order}')
    for f in failures:
        print(f'  {f}')
    raise SystemExit(1)


def select_device_and_power() -> int | None:
    """Select a healthy device, export it as DIRECT_TEST_DEVICE and raise its power limit.

    Returns:
        int | None: The selected device index, or None when HOST_SERVER_URL is unset.
    """

    idx = select_healthy_device()
    if idx is not None:
        os.environ['DIRECT_TEST_DEVICE'] = str(idx)
    set_max_power_limit(first=idx)
    return idx


def prepare_host(models=()) -> None:
    """Reset the host server for a test run.

    Args:
        models (Iterable[str], optional): Prebuilt models to provision. Defaults to none.
    """
    cleanup_all_pipelines(set_power=False)
    select_device_and_power()
    if models:
        ensure_prebuilt_models(models)
