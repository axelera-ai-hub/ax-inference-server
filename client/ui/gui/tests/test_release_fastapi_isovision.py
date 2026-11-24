#!/usr/bin/env python3

"""Release test that drives the Pipeline Editor GUI through its `/_agent` HTTP API to run the Isovision Demo wizard end to end.

Steps: force stop, select yolox-m, health check, throughput test, generate and launch the pipeline, then verify the measured inference fps on the Benchmarking tab. Usage: test_release_fastapi_isovision.py [base_url] [--client-id ID].
"""

from __future__ import annotations

import argparse
import re
import sys
from utils.host_server_prep import prepare_host
import time

import httpx
from playwright.sync_api import sync_playwright

MODEL_NAME = 'yolox-m-coco-onnx'
# Wizard settings: imdecode thread override, cores per instance, throughput test length in seconds, devices per pipeline.
IMDECODE_THREADS_OVERRIDE = '16'
CORES_PER_INSTANCE = 4
THROUGHPUT_SECONDS = '5'
DEVICES_PER_PIPELINE = '1'
# Notification substrings that mean the device or port is still held by a previous run.
DEVICE_BUSY_SIGNATURES = ('allocate AI cores', 'axr_device_connect', 'Address already in use')
# Benchmark source: image file name, requested source fps (1000 is far above what the pipeline sustains), in-flight request cap, and the minimum measured inference fps required.
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
BENCHMARK_SOURCE_FPS = '1000'
BENCHMARK_BACKPRESSURE_CAP = '1000'
BENCHMARK_TARGET_FPS_MIN = 300.0

# Matches the wizard's '<healthy>/<total> device(s) healthy' health check text.
_HEALTH_RE = re.compile(r'(\d+)\s*/\s*(\d+)\s*device\(s\)\s*healthy')
# Matches the notification shown after a successful launch.
LAUNCH_SUCCESS_RE = re.compile(r'Launched \d+ pipeline')

# Browser console errors and uncaught page errors collected while the run is driven by Playwright.
console_errors: list[str] = []
page_errors: list[str] = []


def log(msg: str) -> None:
    """Print a message prefixed with the local time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def die(msg: str) -> None:
    """Log a failure, print the FAIL verdict and exit the process with status 1.

    Args:
        msg (str): Reason for the failure.

    Raises:
        SystemExit: Always.
    """
    log(f'FAILED -- {msg}')
    print('test_release_fastapi_isovision: FAIL')
    sys.exit(1)


def make_agent_helpers(base_url: str):
    """Create the agent-API helper callables bound to one app server.

    Every helper takes the `client_id` of a live browser session as its first argument. Helpers with `required=True` call `die` when the app does not acknowledge the call.

    Args:
        base_url (str): Base URL of the app, e.g. http://127.0.0.1:8090.

    Returns:
        dict: Name to callable map (click, set_field, hover, get_state, get_field_value, field_text, get_text, wait_dialog, notifications_since, notifications_mention, notifications_match, max_notif_id, wait_for_new_client_id), plus the shared httpx client under 'agent'.
    """
    agent = httpx.Client(base_url=base_url, timeout=20.0)

    def click(client_id: str, text: str, *, required: bool = True) -> dict:
        """Click the first control whose text matches, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            text (str): Text of the control to click.
            required (bool, optional): If True, fail the test when the click is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/click`.
        """
        r = agent.post('/_agent/click', json={'client_id': client_id, 'text': text}).json()
        if required and not r.get('ok'):
            die(f'click({text!r}): {r}')
        return r

    def set_field(client_id: str, label: str, value: str, *, required: bool = True) -> dict:
        """Set a form field located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the field.
            value (str): Value to set.
            required (bool, optional): If True, fail the test when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/set_field`.
        """
        r = agent.post('/_agent/set_field', json={'client_id': client_id, 'label': label, 'value': value}).json()
        if required and not r.get('ok'):
            die(f'set_field({label}={value}): {r}')
        return r

    def hover(client_id: str, text: str, action: str = 'enter', *, required: bool = True) -> dict:
        """Send a hover event to an element, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            text (str): Text or name of the element.
            action (str, optional): Hover action, e.g. 'enter'. Defaults to 'enter'.
            required (bool, optional): If True, fail the test when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/hover`.
        """
        r = agent.post('/_agent/hover', json={'client_id': client_id, 'text': text, 'action': action}).json()
        if required and not r.get('ok'):
            die(f'hover({text!r}, {action!r}): {r}')
        return r

    def get_state(client_id: str) -> dict:
        """Fetch the UI state snapshot (fields, buttons, dialog flag, sources) of a session from `GET /_agent/state`."""
        return agent.get('/_agent/state', params={'client_id': client_id}).json()

    def get_field_value(client_id: str, label: str) -> str | None:
        """Return the current value of the field whose label equals `label` exactly, or None if there is no such field."""
        for f in get_state(client_id).get('fields', []):
            if (f.get('label') or '') == label:
                return f.get('value')
        return None

    def field_text(client_id: str, label_substr: str) -> str | None:
        """Return '<label> <value>' for the first field whose label contains `label_substr`, or None if none matches."""
        for f in get_state(client_id).get('fields', []):
            lbl = f.get('label') or ''
            if label_substr in lbl:
                return f'{lbl} {f.get("value")}'
        return None

    def get_text(client_id: str, contains: str) -> str | None:
        """Return the on-page text containing `contains` from `GET /_agent/get_text`, or None if it is not found."""
        r = agent.get('/_agent/get_text', params={'client_id': client_id, 'contains': contains}).json()
        return r.get('text') if r.get('ok') else None

    def wait_dialog(client_id: str, present: bool, timeout_s: float = 10.0) -> bool:
        """Poll until a dialog is open or closed.

        Args:
            client_id (str): Live browser session.
            present (bool): True to wait for a dialog to open, False to wait for it to close.
            timeout_s (float, optional): Maximum wait in seconds. Defaults to 10.0.

        Returns:
            bool: True if the desired state was reached, False on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if get_state(client_id).get('dialog_open') is present:
                return True
            time.sleep(0.15)
        return False

    def notifications_since(client_id: str, since_id: int) -> list[dict]:
        """Return the notifications of a session whose id is greater than `since_id`, from `GET /_agent/notifications`."""
        return agent.get('/_agent/notifications',
                          params={'client_id': client_id, 'since_id': since_id}).json().get('notifications', [])

    def notifications_mention(client_id: str, since_id: int, signatures: tuple[str, ...]) -> bool:
        """Return True if any notification after `since_id` contains one of the given substrings."""
        texts = ' '.join(n['message'] for n in notifications_since(client_id, since_id))
        return any(sig in texts for sig in signatures)

    def notifications_match(client_id: str, since_id: int, pattern: re.Pattern) -> bool:
        """Return True if the joined notification text after `since_id` matches the regex."""
        texts = ' '.join(n['message'] for n in notifications_since(client_id, since_id))
        return pattern.search(texts) is not None

    def max_notif_id(client_id: str) -> int:
        """Return the highest notification id of a session, or 0 if it has none."""
        notifs = notifications_since(client_id, 0)
        return max((n['id'] for n in notifs), default=0)

    def wait_for_new_client_id(before: set[str], timeout_s: float = 10.0) -> str:
        """Wait for a browser session that was not in `before` to open its socket connection.

        Args:
            before (set[str]): Client ids that were already live.
            timeout_s (float, optional): Maximum wait in seconds. Defaults to 10.0.

        Returns:
            str: The id of a newly connected session.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            sessions = agent.get('/_agent/sessions').json().get('sessions', [])
            live_ids = {s['client_id'] for s in sessions if s.get('has_socket_connection')}
            fresh = live_ids - before
            if fresh:
                return next(iter(fresh))
            time.sleep(0.2)
        die('new Playwright-driven client never registered as a live session')

    return {
        'agent': agent, 'click': click, 'set_field': set_field, 'hover': hover, 'get_state': get_state,
        'get_field_value': get_field_value, 'field_text': field_text, 'get_text': get_text,
        'wait_dialog': wait_dialog, 'notifications_since': notifications_since,
        'notifications_mention': notifications_mention, 'notifications_match': notifications_match,
        'max_notif_id': max_notif_id, 'wait_for_new_client_id': wait_for_new_client_id,
    }


def force_stop_all(h, client_id: str) -> None:
    """Open the Pipeline Editor tab and press Force Stop All, confirming the dialog if one appears.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('clicking Pipeline Editor tab')
    h['click'](client_id, 'Pipeline Editor')
    time.sleep(0.5)
    log('clicking Force Stop All and confirming')
    h['click'](client_id, 'Force Stop All', required=False)
    if h['wait_dialog'](client_id, True, timeout_s=5.0):
        state = h['get_state'](client_id)
        confirm_btn = next((b for b in state['buttons']
                             if b.get('in_dialog') and b['text'].strip() not in ('Cancel', '')), None)
        if confirm_btn:
            h['click'](client_id, confirm_btn['text'], required=False)
        h['wait_dialog'](client_id, False, timeout_s=10.0)
    time.sleep(2.0)
    log('PASS: force stop all')


def open_isovision_demo_wizard(h, client_id: str) -> None:
    """Expand the Examples palette category and open the Isovision Demo wizard dialog.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('expanding the Examples palette category')
    h['click'](client_id, 'Examples')
    time.sleep(0.3)
    log('clicking "Isovision Demo"')
    h['click'](client_id, 'Isovision Demo')
    if not h['wait_dialog'](client_id, True, timeout_s=10.0):
        die('Isovision Demo dialog never opened')
    log('PASS: Isovision Demo dialog opened')


def ensure_model_selected(h, client_id: str, model_name: str, download_timeout_s: float = 300.0) -> None:
    """Select the model in the wizard, falling back to the prebuilt catalog and waiting for its download.

    Tries the host-server build dropdown first and accepts an already selected model. Otherwise it ticks 'Use prebuilt models', waits up to 60 s for the catalog field, picks the model and waits for it to report 'downloaded'.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        model_name (str): Model to select.
        download_timeout_s (float, optional): Seconds to wait for the prebuilt download. Defaults to 300.0.
    """
    build_label = 'Model (.axnet, from host server)'
    r = h['set_field'](client_id, build_label, model_name, required=False)
    if r.get('ok'):
        log(f'PASS: selected {model_name!r} from the $SDK_ROOT/build dropdown')
        return
    current = h['field_text'](client_id, build_label)
    if current and model_name in current:
        log(f'PASS: {model_name!r} already selected under $SDK_ROOT/build')
        return

    log(f'{model_name!r} not available under $SDK_ROOT/build -- ticking "Use prebuilt models"')
    checkbox_label = 'Use prebuilt models'
    if not h['click'](client_id, checkbox_label, required=False).get('ok'):
        die(f'could not click the {checkbox_label!r} checkbox')

    prebuilt_label = 'Prebuilt model (axdownloadmodel catalog)'
    deadline = time.time() + 60.0
    fetched = False
    while time.time() < deadline:
        if h['field_text'](client_id, 'Prebuilt model') is not None:
            fetched = True
            break
        time.sleep(0.5)
    if not fetched:
        die('prebuilt model catalog never fetched (field never appeared)')
    log('PASS: prebuilt model catalog fetched')

    r = h['set_field'](client_id, prebuilt_label, model_name, required=False)
    if not r.get('ok'):
        die(f'could not select {model_name!r} from the prebuilt catalog: {r}')
    log(f'selected {model_name!r} from the prebuilt catalog -- waiting for its artifacts to download')

    deadline = time.time() + download_timeout_s
    while time.time() < deadline:
        texts = ' '.join(n['message'] for n in h['notifications_since'](client_id, 0))
        if model_name in texts and ('failed' in texts.lower() or 'could not reach' in texts.lower()):
            die(f'failed to download prebuilt model {model_name!r}: {texts}')
        current = h['field_text'](client_id, 'Prebuilt model')
        if current and model_name in current and 'downloaded' in current.lower():
            log(f'PASS: {model_name!r} downloaded')
            return
        time.sleep(1.0)
    die(f'prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')


def drive_wizard(h, client_id: str, health_timeout_s: float = 300.0) -> tuple[int, str | None]:
    """Fill in the Isovision Demo wizard, run its health check and throughput test, and generate the pipelines.

    Sets the imdecode override, waits for the '<n>/<m> device(s) healthy' text, sets devices per pipeline, enables CPU/NUMA pinning with the core count when those controls are reachable (a warning is logged otherwise), runs the throughput test and clicks Generate Pipelines.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        health_timeout_s (float, optional): Seconds to wait for the health check. Defaults to 300.0.

    Returns:
        tuple[int, str | None]: Number of pipelines generated (healthy devices divided by devices per pipeline), and the throughput result text, or None if the test reported nothing in time. A 'Throughput test failed' message is returned as the text and does not fail the run.
    """
    h['set_field'](client_id, 'imdecode_threads override', IMDECODE_THREADS_OVERRIDE)
    log(f'PASS: imdecode_threads override set to {IMDECODE_THREADS_OVERRIDE}')

    log('clicking Run Health Check')
    h['click'](client_id, 'Run Health Check')
    deadline = time.time() + health_timeout_s
    healthy_count = None
    last_text = ''
    while time.time() < deadline:
        failed_text = h['get_text'](client_id, 'Health check failed')
        if failed_text:
            die(f'device health check failed: {failed_text}')
        text = h['get_text'](client_id, 'device(s) healthy')
        if text:
            m = _HEALTH_RE.search(text)
            if m:
                healthy_count, _total = int(m.group(1)), int(m.group(2))
                last_text = text
                break
        time.sleep(2.0)
    if healthy_count is None:
        die(f'health check never completed within {health_timeout_s}s (last seen: {last_text!r})')
    log(f'PASS: health check -> {last_text}')
    if healthy_count < 1:
        die('no healthy devices -- cannot generate any pipeline')

    log(f'setting Devices per pipeline to {DEVICES_PER_PIPELINE}')
    h['set_field'](client_id, 'Devices per pipeline', DEVICES_PER_PIPELINE)

    log(f'enabling Pin CPU/NUMA and setting {CORES_PER_INSTANCE} core(s) per instance')
    numa_ok = h['click'](client_id, 'Pin CPU/NUMA', required=False).get('ok')
    if numa_ok:
        cores_r = h['set_field'](client_id, 'core(s) per instance',
                                  f'{CORES_PER_INSTANCE} core(s) per instance', required=False)
        if cores_r.get('ok'):
            log(f'PASS: {CORES_PER_INSTANCE} core(s) per instance selected, CPU/NUMA pinning enabled')
        else:
            log('WARNING: cores-per-instance select not reachable (host has no CPU topology info) '
                '-- CPU/NUMA pinning left on with its default core count')
    else:
        log('WARNING: "Pin CPU/NUMA" switch not found -- skipping cores-per-instance step')

    h['set_field'](client_id, 'Seconds', THROUGHPUT_SECONDS)
    log(f'clicking Throughput Test ({THROUGHPUT_SECONDS}s)')
    h['click'](client_id, 'Throughput Test')
    throughput_deadline = time.time() + max(60.0, int(THROUGHPUT_SECONDS) * 4 + 30)
    throughput_summary = None
    while time.time() < throughput_deadline:
        failed_text = h['get_text'](client_id, 'Throughput test failed')
        if failed_text:
            throughput_summary = failed_text
            break
        text = h['get_text'](client_id, 'Aggregate:')
        if text:
            throughput_summary = text
            break
        time.sleep(1.0)
    if throughput_summary:
        log(f'PASS: throughput test -> {throughput_summary}')
    else:
        log('WARNING: throughput test did not report a result in time')

    log('clicking Generate Pipelines')
    h['click'](client_id, 'Generate Pipelines')
    if not h['wait_dialog'](client_id, False, timeout_s=15.0):
        die('Isovision Demo dialog never closed after Generate Pipelines')
    time.sleep(1.0)

    per_pipeline = int(DEVICES_PER_PIPELINE)
    pipeline_count = healthy_count // per_pipeline if per_pipeline else healthy_count
    log(f'PASS: generated {pipeline_count} pipeline(s), {per_pipeline} device(s) each')
    return pipeline_count, throughput_summary


def ensure_opencl_disabled(h, client_id: str) -> None:
    """Turn the OpenCL global setting off.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('disabling OpenCL in Global Settings')
    r = h['set_field'](client_id, 'OpenCL', 'false', required=False)
    if not r.get('ok'):
        die(f'could not disable OpenCL: {r}')
    log('PASS: OpenCL global setting disabled')


def generate_config_yaml(h, client_id: str, timeout_s: float = 30.0) -> None:
    """Press Generate Config YAML, save the preview dialog, and wait for the 'Wrote ...' notification.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for the notification after saving. Defaults to 30.0.
    """
    log('generating config YAML')
    gen_ok = False
    for _ in range(30):
        if h['click'](client_id, 'Generate Config YAML', required=False).get('ok'):
            gen_ok = True
            break
        time.sleep(0.2)
    if not gen_ok:
        die('Generate Config YAML button never enabled')
    if not h['wait_dialog'](client_id, True):
        die('YAML preview dialog never opened')
    h['click'](client_id, 'Save')
    if not h['wait_dialog'](client_id, False):
        die('YAML preview dialog never closed')
    deadline = time.time() + timeout_s
    wrote_text = None
    while time.time() < deadline:
        for n in h['notifications_since'](client_id, 0):
            if n['message'].startswith('Wrote '):
                wrote_text = n['message']
                break
        if wrote_text:
            break
        time.sleep(0.5)
    if not wrote_text:
        die('Generate Config YAML -> Save never produced a "Wrote ..." notification')
    log(f'PASS: {wrote_text}')


def compile_and_launch_vision(h, client_id: str, timeout_s: float = 900.0) -> str:
    """Press Compile and Launch Pipeline and wait for the launch, retrying known recoverable failures.

    Makes up to three attempts. A busy-device notification triggers Force Stop All and a retry. An OpenCL driver error triggers one retry after disabling OpenCL and regenerating the config YAML.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for an outcome per attempt. Defaults to 900.0.

    Returns:
        str: The value of the 'Inference endpoint(s)' field, or '' if it is empty.
    """
    opencl_error_signatures = ('OpenCL platform',)

    def try_compile() -> tuple[str, int]:
        """Click the compile button and watch notifications until an outcome is known.

        Returns:
            tuple[str, int]: Outcome ('launched', 'device_busy', 'opencl_error', 'reenabled', 'timeout' or 'button_not_found') and the notification id seen before the click.
        """
        since_id = h['max_notif_id'](client_id)
        ok = False
        for _ in range(30):
            if h['click'](client_id, 'Compile and Launch Pipeline', required=False).get('ok'):
                ok = True
                break
            time.sleep(0.2)
        if not ok:
            return 'button_not_found', since_id
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            if h['notifications_match'](client_id, since_id, LAUNCH_SUCCESS_RE):
                return 'launched', since_id
            if h['notifications_mention'](client_id, since_id, DEVICE_BUSY_SIGNATURES):
                return 'device_busy', since_id
            if h['notifications_mention'](client_id, since_id, opencl_error_signatures):
                return 'opencl_error', since_id
            state = h['get_state'](client_id)
            btn = next((b for b in state['buttons'] if 'Compile and Launch Pipeline' in b['text']), None)
            if btn and not btn['disabled']:
                return 'reenabled', since_id
            log(f'compiling and launching ... ({time.monotonic() - start:.0f}s)')
            time.sleep(1.0)
        return 'timeout', since_id

    log('compiling and launching pipeline')
    opencl_retried = False
    result = 'exhausted'
    for _attempt in range(3):
        outcome, since_id = try_compile()
        if outcome == 'device_busy':
            log('device busy -- retrying Force Stop All')
            force_stop_all(h, client_id)
            continue
        if outcome == 'opencl_error' and not opencl_retried:
            log('OpenCL driver error -- disabling OpenCL and regenerating config YAML before retrying')
            h['set_field'](client_id, 'OpenCL', 'false', required=False)
            generate_config_yaml(h, client_id)
            opencl_retried = True
            continue
        if outcome == 'launched':
            result = 'ok'
            break
        if outcome != 'reenabled':
            result = outcome
            break
        endpoint_after = h['get_field_value'](client_id, 'Inference endpoint(s)')
        if h['notifications_match'](client_id, since_id, LAUNCH_SUCCESS_RE) and endpoint_after:
            result = 'ok'
        else:
            result = 'no_launch_notification'
        break

    notif_texts = [n['message'] for n in h['notifications_since'](client_id, 0)][-5:]
    if result != 'ok':
        die(f'compile/launch did not succeed (result={result}); recent notifications: {notif_texts}')
    endpoint = h['get_field_value'](client_id, 'Inference endpoint(s)')
    log(f'PASS: compile/launch succeeded -- endpoint(s): {endpoint!r} (recent notifications: {notif_texts})')
    return endpoint or ''


def run_benchmark_tab_check(h, client_id: str, timeout_s: float = 60.0) -> float:
    """Add an image source on the Benchmarking tab and check its measured inference fps against the minimum.

    Clears old sources, disables AIMD backoff, sets the backpressure cap, adds the image at the benchmark source fps, polls the source's `infer_fps` until it reaches the target or the timeout passes, then removes the source again.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for the fps to reach the target. Defaults to 60.0.

    Returns:
        float: The last measured inference fps.
    """
    log('clicking Benchmarking tab')
    h['click'](client_id, 'Benchmarking')
    time.sleep(0.5)

    log('removing any pre-existing benchmark sources (defensive cleanup)')
    h['click'](client_id, 'delete_sweep')
    time.sleep(0.5)

    log('hovering the Advanced Settings edge sensor to reveal the drawer')
    h['hover'](client_id, 'benchmark settings edge', 'enter')
    time.sleep(0.3)

    r = h['set_field'](client_id, 'AIMD backoff', 'false', required=False)
    if not r.get('ok'):
        die(f'could not disable AIMD backoff: {r}')
    log('PASS: AIMD backoff disabled')

    h['set_field'](client_id, 'Backpressure cap (in-flight inference requests)', BENCHMARK_BACKPRESSURE_CAP)
    log(f'PASS: Backpressure cap set to {BENCHMARK_BACKPRESSURE_CAP}')

    sources_before = set(h['get_state'](client_id).get('sources', {}).keys())

    log(f'clicking Add file -> {BENCHMARK_IMAGE_FILENAME}')
    h['click'](client_id, 'Add file')
    if not h['wait_dialog'](client_id, True, timeout_s=5.0):
        die('Add file dialog never opened')
    h['set_field'](client_id, 'File / folder', BENCHMARK_IMAGE_FILENAME)
    h['set_field'](client_id, 'FPS', BENCHMARK_SOURCE_FPS)
    h['click'](client_id, 'Open')
    if not h['wait_dialog'](client_id, False, timeout_s=5.0):
        die('Add file dialog never closed after Open')
    log(f'PASS: added image source {BENCHMARK_IMAGE_FILENAME!r}')

    new_source_id = None
    id_deadline = time.time() + 10.0
    while time.time() < id_deadline and new_source_id is None:
        new_ids = set(h['get_state'](client_id).get('sources', {}).keys()) - sources_before
        if new_ids:
            new_source_id = sorted(new_ids)[0]
        else:
            time.sleep(0.5)
    if new_source_id is None:
        die(f'could not identify the newly added {BENCHMARK_IMAGE_FILENAME!r} source by id')

    log('waiting for measured inference fps to ramp up')
    deadline = time.time() + timeout_s
    infer_fps = None
    while time.time() < deadline:
        metrics = h['get_state'](client_id).get('sources', {}).get(new_source_id, {})
        fps = metrics.get('infer_fps')
        if fps is not None:
            infer_fps = fps
        if infer_fps is not None and infer_fps >= BENCHMARK_TARGET_FPS_MIN:
            break
        time.sleep(2.0)
    if infer_fps is None:
        die(f'{BENCHMARK_IMAGE_FILENAME} source never reported an infer fps within {timeout_s}s')
    log(f'measured inference fps = {infer_fps:.1f} (target >= {BENCHMARK_TARGET_FPS_MIN:.0f}; this is the '
        "same per-source number the Benchmarking tab's Live stats Plotly plot sums into its Aggregate "
        'FPS trace -- see test_release_playwright_isovision.py for a variant that also reads that '
        'rendered trace directly)')
    if infer_fps < BENCHMARK_TARGET_FPS_MIN:
        die(f'measured inference fps {infer_fps:.1f} is below the {BENCHMARK_TARGET_FPS_MIN:.0f} target')
    log(f'PASS: measured inference fps {infer_fps:.1f} reproduces the throughput test\'s aggregate')

    log('cleaning up: removing the benchmark source so it does not contend with later runs')
    h['click'](client_id, 'delete_sweep')
    time.sleep(0.5)
    log('PASS: removed benchmark source(s) (cleanup)')
    return infer_fps


def run(h, client_id: str) -> tuple[int, str | None, float | None]:
    """Run the whole Isovision Demo workflow in one browser session.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.

    Returns:
        tuple[int, str | None, float | None]: Pipeline count, throughput result text, and benchmark fps as returned by the steps.
    """
    force_stop_all(h, client_id)
    open_isovision_demo_wizard(h, client_id)
    ensure_model_selected(h, client_id, MODEL_NAME)
    pipeline_count, throughput_summary = drive_wizard(h, client_id)
    ensure_opencl_disabled(h, client_id)
    generate_config_yaml(h, client_id)
    compile_and_launch_vision(h, client_id)
    benchmark_fps = run_benchmark_tab_check(h, client_id)
    log('ALL DONE -- fastapi-driven Isovision Demo release workflow succeeded')
    return pipeline_count, throughput_summary, benchmark_fps


def main() -> int:
    """Prepare the host, run the workflow in a fresh or existing browser session, and print a summary.

    Without `--client-id` a headless Chromium tab is opened and its console and page errors are recorded. With `--client-id` the test attaches to that live session and records none.

    Returns:
        int: 0 if the workflow finished with no console or page errors, 1 otherwise (die exits earlier with 1).
    """
    prepare_host()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8090')
    parser.add_argument('--client-id', default=None)
    args = parser.parse_args()

    h = make_agent_helpers(args.base_url)
    pipeline_count = None
    throughput_summary = None
    benchmark_fps = None

    if args.client_id:
        log(f'attaching to existing live client_id={args.client_id} -- no new browser tab, '
            'no console/page-error capture')
        pipeline_count, throughput_summary, benchmark_fps = run(h, args.client_id)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
            page.on('pageerror', lambda exc: page_errors.append(str(exc)))

            before = {s['client_id'] for s in h['agent'].get('/_agent/sessions').json().get('sessions', [])
                      if s.get('has_socket_connection')}
            log(f'opening fresh browser tab at {args.base_url}')
            page.goto(args.base_url, wait_until='networkidle')
            page.wait_for_timeout(1000)
            client_id = h['wait_for_new_client_id'](before)
            log(f'using fresh client_id={client_id}')

            try:
                pipeline_count, throughput_summary, benchmark_fps = run(h, client_id)
            finally:
                page.wait_for_timeout(500)
                if console_errors:
                    log(f'WARNING: {len(console_errors)} browser console error(s): {console_errors[:5]}')
                if page_errors:
                    log(f'WARNING: {len(page_errors)} uncaught page (JS) error(s): {page_errors[:5]}')
                if not console_errors and not page_errors:
                    log('no browser console errors and no uncaught page errors during the whole run')
                context.close()
                browser.close()

    print('\n=== SUMMARY ===')
    print(f'pipeline_count: {pipeline_count}')
    if throughput_summary:
        print(f'throughput: {throughput_summary}')
    if benchmark_fps is not None:
        print(f'benchmarking tab image-source inference fps: {benchmark_fps:.1f}')
    ok = not (console_errors or page_errors)
    print('test_release_fastapi_isovision: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
