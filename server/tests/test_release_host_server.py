#!/usr/bin/env python3

"""Run release smoke checks against a live host server's REST API.

Checks health, authentication, device and model endpoints, optional axdevice hardware steps, the device health check, and optionally a server restart. Prints "test_release_host_server: PASS" and exits 0 on success; exits 1 on the first failure.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

_HEALTH_POLL_INTERVAL_S = 2.0
_DEFAULT_HEALTH_TIMEOUT_S = 180.0
_RESTART_POLL_INTERVAL_S = 1.0
_RESTART_TIMEOUT_S = 30.0


def log(msg: str) -> None:
    """Print a message prefixed with the local time (HH:MM:SS), flushed."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def die(msg: str) -> None:
    """Log a failure, print the FAIL marker and exit the process with status 1."""
    log(f'FAILED -- {msg}')
    print('test_release_host_server: FAIL')
    sys.exit(1)


def warn(msg: str) -> None:
    """Log a non-fatal warning."""
    log(f'WARNING: {msg}')


def _parse_args(argv=None):
    """Parse command-line arguments.

    base_url defaults to $HOST_SERVER_URL; the API key is read from $HOST_SERVER_API_KEY in main().

    Args:
        argv (list[str] | None, optional): Arguments to parse. Defaults to sys.argv.

    Returns:
        argparse.Namespace: The parsed options.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base_url', nargs='?', default=os.environ.get('HOST_SERVER_URL', '').rstrip('/'))
    ap.add_argument('--health-timeout', type=float, default=_DEFAULT_HEALTH_TIMEOUT_S)
    ap.add_argument('--skip-cleanup', action='store_true',
                     help='skip POST /api/v1/pipelines/cleanup-all before the device health check')
    ap.add_argument('--axdevice-device', type=int, default=None, metavar='N',
                     help='also refresh, reload firmware and set/verify the power limit on device N '
                          '(resets real hardware; skipped unless given)')
    ap.add_argument('--axdevice-power', type=float, default=20.0, metavar='W',
                     help='power limit in watts to set and read back with --axdevice-device (default 20)')
    ap.add_argument('--include-restart', action='store_true',
                     help='also exercise POST /api/v1/server/restart (kills+relaunches the live process)')
    return ap.parse_args(argv)


def _check_monitor_power(stats: dict) -> None:
    """Validate measured power in a /api/v1/monitor/stats response.

    Fails if any present power_sensor_0_w or power_sensor_1_w reading is not positive; warns if no device reports any measurement.

    Args:
        stats (dict): Decoded JSON body of the monitor stats endpoint.
    """
    metered = {}
    for idx, dev in stats.get('devices', {}).items():
        sensors = {k: dev.get(k) for k in ('power_sensor_0_w', 'power_sensor_1_w') if dev.get(k) is not None}
        if any(v <= 0 for v in sensors.values()):
            die(f'/api/v1/monitor/stats device {idx}: non-positive measured power {sensors}')
        if sensors:
            metered[idx] = sensors
    if metered:
        log(f'PASS: /api/v1/monitor/stats reports measured power (W) for device(s) {metered}')
    else:
        warn('/api/v1/monitor/stats reports no measured power on any device (no power sensors, or no measurements yet)')


def _axdevice_post(client, dev: int, body: dict, label: str) -> dict:
    """POST an axdevice request (with confirm=True) and require success.

    Fails unless the HTTP status is 200, the body has ok set, and device_after is truthy. Uses a 420 s timeout.

    Args:
        client (httpx.Client): Authenticated client.
        dev (int): Device index.
        body (dict): Request body; "confirm": True is added.
        label (str): Description used in failure messages.

    Returns:
        dict: The decoded response body.
    """
    r = client.post(f'/api/v1/devices/{dev}/axdevice', json={**body, 'confirm': True}, timeout=420.0)
    if r.status_code != 200:
        die(f'POST /api/v1/devices/{dev}/axdevice ({label}) -> {r.status_code}: {r.text[:300]}')
    data = r.json()
    if not data.get('ok'):
        die(f'axdevice {label} on device {dev} failed: {[(s["step"], s["returncode"], s["stderr"][:200]) for s in data["steps"]]}')
    if not data.get('device_after'):
        die(f'device {dev} did not enumerate after {label}')
    return data


def _axdevice_read_power(client, dev: int):
    """Read the current power limit from GET /api/v1/devices/{dev}/axdevice.

    Args:
        client (httpx.Client): Authenticated client.
        dev (int): Device index.

    Returns:
        tuple: (power_limit_w, device) from the response; either may be None.
    """
    r = client.get(f'/api/v1/devices/{dev}/axdevice')
    if r.status_code != 200:
        die(f'GET /api/v1/devices/{dev}/axdevice -> {r.status_code}: {r.text[:200]}')
    return r.json().get('power_limit_w'), r.json().get('device')


def _axdevice_hardware_steps(client, dev: int, power_w: float) -> None:
    """Exercise axdevice refresh, firmware reload and power-limit set/restore on a real device.

    Sets power_w, verifies it through GET and AxMonitor (the latter only warns on mismatch), checks it survives a refresh, then restores the original limit. If the device reports no power limit, the power steps are skipped. Resets real hardware.

    Args:
        client (httpx.Client): Authenticated client.
        dev (int): Device index.
        power_w (float): Power limit in watts to set.
    """
    original, line = _axdevice_read_power(client, dev)
    log(f'axdevice device {dev} before: power_limit_w={original}  ({line})')

    _axdevice_post(client, dev, {'action': 'refresh'}, 'refresh')
    log(f'PASS: axdevice refresh on device {dev}')
    _axdevice_post(client, dev, {'action': 'reload_firmware'}, 'reload_firmware')
    log(f'PASS: axdevice reload_firmware on device {dev}')

    if original is None:
        warn(f'device {dev} reports no power-limit in axdevice -v; skipping the set/verify power steps')
        return

    want = power_w
    data = _axdevice_post(client, dev, {'power_limit_w': want}, f'set_power_limit {want:g}')
    got, line = _axdevice_read_power(client, dev)
    if got != want or data.get('power_limit_w_after') != want:
        die(f'power limit on device {dev}: set {want:g} W, read back POST={data.get("power_limit_w_after")} GET={got} ({line})')
    log(f'PASS: power limit set to {want:g} W on device {dev} and read back via GET')
    r = client.get('/api/v1/monitor/stats')
    if r.status_code == 200:
        mon = r.json().get('devices', {}).get(str(dev), {}).get('power_limit_w')
        if mon == want:
            log(f'PASS: AxMonitor also reports power limit {mon:g} W for device {dev}')
        else:
            warn(f'AxMonitor reports power limit {mon} for device {dev} (expected {want:g}); it may lag or index devices differently')

    _axdevice_post(client, dev, {'action': 'refresh'}, 'refresh (power persistence)')
    got, _ = _axdevice_read_power(client, dev)
    if got != want:
        die(f'power limit on device {dev} was {want:g} W before refresh but reads {got} after it')
    log(f'PASS: power limit {want:g} W persisted across a refresh on device {dev}')

    _axdevice_post(client, dev, {'power_limit_w': original}, f'restore power limit {original}')
    got, _ = _axdevice_read_power(client, dev)
    if got != original:
        die(f'could not restore device {dev} power limit to {original} (reads {got})')
    log(f'PASS: restored device {dev} power limit to {original}')


def main(argv=None) -> int:
    """Run the release checks in order.

    Requires a base URL (argument or HOST_SERVER_URL) and HOST_SERVER_API_KEY. Failures call die() and exit 1.

    Args:
        argv (list[str] | None, optional): Arguments to parse. Defaults to sys.argv.

    Returns:
        int: 0 if all checks passed.
    """
    args = _parse_args(argv)
    if not args.base_url:
        die('no base_url given and HOST_SERVER_URL is not set')
    api_key = os.environ.get('HOST_SERVER_API_KEY', '')
    if not api_key:
        die('HOST_SERVER_API_KEY is not set in the environment')

    auth_client = httpx.Client(base_url=args.base_url, headers={'X-API-Key': api_key}, timeout=30.0)
    noauth_client = httpx.Client(base_url=args.base_url, timeout=10.0)

    r = noauth_client.get('/api/v1/health')
    if r.status_code != 200:
        die(f'GET /api/v1/health -> {r.status_code}: {r.text[:200]}')
    log('PASS: /api/v1/health reachable')

    r = noauth_client.get('/api/v1/devices')
    if r.status_code != 401:
        die(f'GET /api/v1/devices with no X-API-Key -> expected 401, got {r.status_code}: {r.text[:200]}')
    bad_client = httpx.Client(base_url=args.base_url, headers={'X-API-Key': 'not-the-real-key'}, timeout=10.0)
    r = bad_client.get('/api/v1/devices')
    if r.status_code != 401:
        die(f'GET /api/v1/devices with a wrong X-API-Key -> expected 401, got {r.status_code}')
    log('PASS: auth correctly rejects missing/wrong X-API-Key')

    r = auth_client.get('/api/v1/devices')
    if r.status_code != 200:
        die(f'GET /api/v1/devices -> {r.status_code}: {r.text[:200]}')
    devices = r.json().get('devices', [])
    log(f'PASS: /api/v1/devices -> {len(devices)} device(s): {[d.get("index") for d in devices]}')

    if devices:
        first = devices[0].get('index', 0)
        for body, want, label in (
            ({'action': 'refresh'}, 400, 'no confirm'),
            ({'confirm': True}, 422, 'empty request'),
        ):
            r = auth_client.post(f'/api/v1/devices/{first}/axdevice', json=body)
            if r.status_code != want:
                die(f'POST /api/v1/devices/{first}/axdevice ({label}) -> expected {want}, got {r.status_code}: {r.text[:200]}')
        r = auth_client.post('/api/v1/devices/99999/axdevice', json={'action': 'refresh', 'confirm': True})
        if r.status_code != 404:
            die(f'POST /api/v1/devices/99999/axdevice (unknown device) -> expected 404, got {r.status_code}: {r.text[:200]}')
        r = noauth_client.post(f'/api/v1/devices/{first}/axdevice', json={'action': 'refresh', 'confirm': True})
        if r.status_code != 401:
            die(f'POST /api/v1/devices/{first}/axdevice with no X-API-Key -> expected 401, got {r.status_code}')
        r = auth_client.get('/api/v1/devices/99999/axdevice')
        if r.status_code != 404:
            die(f'GET /api/v1/devices/99999/axdevice (unknown device) -> expected 404, got {r.status_code}: {r.text[:200]}')
        r = noauth_client.get(f'/api/v1/devices/{first}/axdevice')
        if r.status_code != 401:
            die(f'GET /api/v1/devices/{first}/axdevice with no X-API-Key -> expected 401, got {r.status_code}')
        r = auth_client.get(f'/api/v1/devices/{first}/axdevice')
        if r.status_code != 200 or r.json().get('device_id') != first or not r.json().get('device'):
            die(f'GET /api/v1/devices/{first}/axdevice -> {r.status_code}: {r.text[:200]}')
        log(f'PASS: /api/v1/devices/{{id}}/axdevice rejects no-confirm, empty, unknown-device and unauthenticated requests; '
            f'GET reads device {first} (power_limit_w={r.json().get("power_limit_w")})')

    for path, label in (
        ('/api/v1/sdk-root', 'sdk-root'),
        ('/api/v1/models', 'models'),
        ('/api/v1/prebuilt-models', 'prebuilt-models'),
    ):
        r = auth_client.get(path)
        if r.status_code != 200:
            die(f'GET {path} -> {r.status_code}: {r.text[:200]}')
        log(f'PASS: {path}')

    for path in ('/api/v1/devices/cpu_topology', '/api/v1/devices/numa_plan', '/api/v1/monitor/stats'):
        r = auth_client.get(path)
        if r.status_code == 200:
            log(f'PASS: {path}')
            if path.endswith('/monitor/stats'):
                _check_monitor_power(r.json())
        else:
            warn(f'{path} -> {r.status_code}: {r.text[:200]}')

    for path in ('/api/v1/monitor/workers', '/api/v1/vllm/status', '/api/v1/vllm/artifacts',
                 '/api/v1/benchmark-media/status'):
        r = auth_client.get(path)
        if r.status_code != 200:
            die(f'GET {path} -> {r.status_code}: {r.text[:200]}')
        log(f'PASS: {path}')

    if not args.skip_cleanup:
        r = auth_client.post('/api/v1/pipelines/cleanup-all')
        if r.status_code != 200:
            die(f'POST /api/v1/pipelines/cleanup-all -> {r.status_code}: {r.text[:200]}')
        log(f'PASS: /api/v1/pipelines/cleanup-all -> {r.json()}')
    else:
        log('skipping /api/v1/pipelines/cleanup-all (--skip-cleanup given)')

    if args.axdevice_device is not None:
        _axdevice_hardware_steps(auth_client, args.axdevice_device, args.axdevice_power)

    r = auth_client.post('/api/v1/devices/health/all/start')
    if r.status_code != 200:
        die(f'POST /api/v1/devices/health/all/start -> {r.status_code}: {r.text[:200]}')
    log(f'health check started: {r.json()}')

    deadline = time.time() + args.health_timeout
    status = None
    while time.time() < deadline:
        r = auth_client.get('/api/v1/devices/health/status')
        if r.status_code != 200:
            die(f'GET /api/v1/devices/health/status -> {r.status_code}: {r.text[:200]}')
        status = r.json()
        if status.get('error'):
            die(f'device health check reported an error: {status["error"]}')
        if status.get('done'):
            break
        time.sleep(_HEALTH_POLL_INTERVAL_S)
    if status is None or not status.get('done'):
        die(f'device health check never completed within {args.health_timeout}s (last status: {status})')

    healthy, total = status.get('healthy_count', 0), status.get('total', 0)
    log(f'PASS: device health check completed -- host_server.py correctly ran it to completion '
        f'({healthy}/{total} healthy)')
    if total == 0:
        warn('no devices enumerated at all')
    elif healthy < total:
        warn(f'only {healthy}/{total} device(s) came back healthy -- see status.devices for per-device errors '
             f'(this is a device/firmware concern, not a host_server.py fault): {status.get("devices")}')

    if args.include_restart:
        log('calling POST /api/v1/server/restart (--include-restart given)')
        r = auth_client.post('/api/v1/server/restart')
        if r.status_code != 200:
            die(f'POST /api/v1/server/restart -> {r.status_code}: {r.text[:200]}')
        log(f'restart scheduled: {r.json()}')
        time.sleep(3.0)
        restart_deadline = time.time() + _RESTART_TIMEOUT_S
        back_up = False
        while time.time() < restart_deadline:
            try:
                r = noauth_client.get('/api/v1/health')
                if r.status_code == 200:
                    back_up = True
                    break
            except httpx.TransportError:
                pass
            time.sleep(_RESTART_POLL_INTERVAL_S)
        if not back_up:
            die(f'host_server.py did not come back up within {_RESTART_TIMEOUT_S}s of /api/v1/server/restart')
        log('PASS: host_server.py restarted itself and came back up')

    print('=== SUMMARY ===')
    print(f'devices: {len(devices)}, device health: {healthy}/{total} healthy')
    print('test_release_host_server: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
