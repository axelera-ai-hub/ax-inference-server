#!/usr/bin/env python3

"""Release test that drives the Pipeline Editor GUI through its `/_agent` HTTP API to run the Three-Stage Conditional Cascade wizard end to end.

Steps: force stop, configure the yolox-m, yolo26npose and retinaface stages and the condition, health check, generate and launch the pipeline, then sweep the source fps on the Benchmarking tab. Usage: test_release_fastapi_cascade3.py [base_url] [--client-id ID].
"""

from __future__ import annotations

import argparse
import re
import sys
from utils.host_server_prep import prepare_host
import time

import httpx
from playwright.sync_api import sync_playwright

PRIMARY_MODEL = 'yolox-m-coco-onnx'
SECONDARY_MODEL = 'yolo26npose-coco-onnx'
TERTIARY_MODEL = 'retinaface-mobilenet0.25-widerface-onnx'
IMDECODE_THREADS_OVERRIDE = '16'
FILTER_CLASSES = '0'
# Cores per stage on one device, and the condition that gates the tertiary stage.
PRIMARY_CORES = '1'
SECONDARY_CORES = '2'
TERTIARY_CORES = '1'
PREDICATE_TYPE = 'kpts_conf_gt'
PREDICATE_META_KEY = 'pose'
PREDICATE_INDICES = '0,1,2'
PREDICATE_VALUE = '0.5'
# Notification substrings that mean the device or port is still held by a previous run.
DEVICE_BUSY_SIGNATURES = ('allocate AI cores', 'axr_device_connect', 'Address already in use',
                           'a device health check is currently using')
# Notification substrings that mean the device faulted while compiling or launching.
DEVICE_FAULT_SIGNATURES = ('faulty device(s) detected', 'ZE_RESULT_ERROR_DEVICE_LOST')
# Wizard section labels, which are also the prefixes of the health check lines.
STAGE_LABELS = ['Primary model', 'Secondary model', 'Conditional tertiary model']
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
BENCHMARK_SOURCE_FPS = '1000'
# In-flight request cap set in the benchmark settings.
BENCHMARK_BACKPRESSURE_CAP = '1000'
# Performance gate: source fps steps to hold, then settle and hold times per step (s), sample spacing (s), allowed relative deviation, retries with a longer hold, and the hold growth factor per retry.
FPS_STEPS = [5, 10, 15, 30]
FPS_GATE_SETTLE_S = 2.0
FPS_GATE_HOLD_S = 8.0
FPS_GATE_SAMPLE_INTERVAL_S = 2.0
FPS_GATE_TOLERANCE_FRAC = 0.15
FPS_GATE_MAX_RETRIES = 2
FPS_GATE_HOLD_GROWTH = 2.0

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
    print('test_release_fastapi_cascade3: FAIL')
    sys.exit(1)


def make_agent_helpers(base_url: str):
    """Create the agent-API helper callables bound to one app server.

    Every helper takes the `client_id` of a live browser session as its first argument. Helpers with `required=True` call `die` when the app does not acknowledge the call.

    Args:
        base_url (str): Base URL of the app, e.g. http://127.0.0.1:8090.

    Returns:
        dict: Name to callable map (click, set_field, hover, toggle_dropdown, read_dropdown_options, get_state, get_field_value, get_text, wait_dialog, notifications_since, notifications_mention, notifications_match, max_notif_id, wait_for_new_client_id), plus the shared httpx client under 'agent'.
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

    def toggle_dropdown(client_id: str, label: str, *, required: bool = True) -> dict:
        """Open or close a dropdown located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the dropdown.
            required (bool, optional): If True, fail the test when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/toggle_dropdown`.
        """
        r = agent.post('/_agent/toggle_dropdown', json={'client_id': client_id, 'label': label}).json()
        if required and not r.get('ok'):
            die(f'toggle_dropdown({label!r}): {r}')
        return r

    def read_dropdown_options(client_id: str, label: str, *, required: bool = True) -> dict:
        """Read the options of a dropdown located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the dropdown.
            required (bool, optional): If True, fail the test when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/read_dropdown_options`; its `options` list holds dicts with `text` and `selected`.
        """
        r = agent.post('/_agent/read_dropdown_options', json={'client_id': client_id, 'label': label}).json()
        if required and not r.get('ok'):
            die(f'read_dropdown_options({label!r}): {r}')
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
        'toggle_dropdown': toggle_dropdown, 'read_dropdown_options': read_dropdown_options,
        'get_field_value': get_field_value, 'get_text': get_text, 'wait_dialog': wait_dialog,
        'notifications_since': notifications_since, 'notifications_mention': notifications_mention,
        'notifications_match': notifications_match, 'max_notif_id': max_notif_id,
        'wait_for_new_client_id': wait_for_new_client_id,
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


def open_three_stage_cascade_wizard(h, client_id: str) -> None:
    """Expand the Examples palette category and open the Three-Stage Conditional Cascade wizard dialog.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('expanding the Examples palette category')
    h['click'](client_id, 'Examples')
    time.sleep(0.3)
    log('clicking "Three-Stage Conditional Cascade"')
    h['click'](client_id, 'Three-Stage Conditional Cascade')
    if not h['wait_dialog'](client_id, True, timeout_s=10.0):
        die('Three-Stage Conditional Cascade dialog never opened')
    log('PASS: Three-Stage Conditional Cascade dialog opened')


def configure_stage(h, client_id: str, stage_label: str, model_name: str, cores: str, meta_key: str,
                     download_timeout_s: float = 300.0) -> None:
    """Configure one wizard stage: model, meta key override and cores on device 0.

    Opens the stage's section (except the primary one) and selects the model from the host-server build dropdown. If that fails it enables 'Use prebuilt models', selects the model from the catalog and waits for its download. Any failure ends the test through `die`.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        stage_label (str): Section label, e.g. 'Primary model'.
        model_name (str): Model to select.
        cores (str): Number of cores on device 0.
        meta_key (str): Value for the stage's meta_key_override field.
        download_timeout_s (float, optional): Seconds to wait for a prebuilt download. Defaults to 300.0.
    """

    if stage_label != 'Primary model':
        h['click'](client_id, stage_label)
        time.sleep(0.3)
    r = h['set_field'](client_id, 'Model (.axnet, from host server)', model_name, required=False)
    if r.get('ok'):
        log(f'PASS: {stage_label}: selected {model_name!r} from the $SDK_ROOT/build dropdown')
    else:
        log(f'{stage_label}: {model_name!r} not available under $SDK_ROOT/build ({r}) -- '
            'falling back to prebuilt models')
        toggle_r = h['set_field'](client_id, 'Use prebuilt models', 'true', required=False)
        if not toggle_r.get('ok'):
            die(f'{stage_label}: could not enable "Use prebuilt models": {toggle_r}')

        deadline = time.time() + 60.0
        prebuilt_r: dict = {}
        while time.time() < deadline:
            prebuilt_r = h['set_field'](client_id, 'Prebuilt model (axdownloadmodel catalog)', model_name,
                                         required=False)
            if prebuilt_r.get('ok') or prebuilt_r.get('error') == 'option_not_found':
                break
            time.sleep(1.0)
        if not prebuilt_r.get('ok'):
            die(f'{stage_label}: {model_name!r} not found in the prebuilt catalog: {prebuilt_r}')
        log(f'{stage_label}: selected {model_name!r} from the prebuilt catalog -- '
            'waiting for its artifacts to download')

        deadline = time.time() + download_timeout_s
        downloaded = False
        while time.time() < deadline:
            notif_texts = ' '.join(n['message'] for n in h['notifications_since'](client_id, 0))
            if model_name in notif_texts and ('failed' in notif_texts.lower()
                                               or 'could not reach' in notif_texts.lower()):
                die(f'failed to download prebuilt model {model_name!r}: {notif_texts}')
            current = h['get_field_value'](client_id, 'Prebuilt model (axdownloadmodel catalog)') or ''
            if model_name in current and 'downloaded' in current.lower():
                downloaded = True
                break
            time.sleep(1.0)
        if not downloaded:
            die(f'prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')
        log(f'PASS: {stage_label}: {model_name!r} downloaded')
    h['set_field'](client_id, 'meta_key_override', meta_key)
    cores_r = h['set_field'](client_id, 'Cores on Device 0', cores, required=False)
    if not cores_r.get('ok'):
        die(f'{stage_label}: could not set cores on Device 0 to {cores}: {cores_r}')
    log(f'PASS: {stage_label} set to {model_name}, device 0, {cores} core(s), meta_key_override={meta_key}')


def select_device(h, client_id: str, stage_label: str, device: int, cores: str) -> None:
    """Move one wizard stage from device 0 to another device and set its cores there.

    Opens the stage's Devices dropdown, deselects any other selected device, selects the target one and sets 'Cores on Device <device>'.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        stage_label (str): Section label of the stage.
        device (int): Index of the device to use.
        cores (str): Number of cores on that device.
    """

    h['click'](client_id, stage_label)
    time.sleep(0.3)
    label = 'Devices (select one or more)'
    h['toggle_dropdown'](client_id, label)
    options = h['read_dropdown_options'](client_id, label).get('options', [])
    target_text = None
    already_selected = False
    for opt in options:
        m = re.match(r'device\s+(\d+)\b', (opt.get('text') or '').strip(), re.IGNORECASE)
        if not m:
            continue
        idx = int(m.group(1))
        if idx == device:
            target_text = opt['text']
            already_selected = bool(opt.get('selected'))
        elif opt.get('selected'):
            h['set_field'](client_id, label, opt['text'])
    if target_text is None:
        die(f'{stage_label}: device {device} not found among dropdown options: '
            f'{[o.get("text") for o in options]}')
    if not already_selected:
        r = h['set_field'](client_id, label, target_text)
        if not r.get('ok'):
            die(f'{stage_label}: could not select device {device}: {r}')
    close_r = h['toggle_dropdown'](client_id, label, required=False)
    if close_r.get('is_open'):
        h['toggle_dropdown'](client_id, label, required=False)
    cores_r = h['set_field'](client_id, f'Cores on Device {device}', cores, required=False)
    if not cores_r.get('ok'):
        die(f'{stage_label}: could not set cores on device {device} to {cores}: {cores_r}')
    log(f'PASS: {stage_label} moved to device {device}, {cores} core(s)')


def healthy_device_candidates(health_text: str, stage_labels: list[str]) -> list[int]:
    """Work out which devices passed the health check for every stage.

    Parses lines of the form '<label>: <n>/<m> device(s) healthy (indices: 0, 1)'.

    Args:
        health_text (str): Health check text from the wizard.
        stage_labels (list[str]): Stage labels that must each have a line.

    Returns:
        list[int]: Device indices healthy for every stage, device 0 first and the rest ascending. Empty if a stage has no line or no device is common to all.
    """
    per_stage: dict[str, set[int]] = {}
    for line in health_text.split('\n'):
        m = re.match(r'^(.*?):\s*\d+/\d+ device\(s\) healthy \(indices:\s*(.*?)\)\s*$', line.strip())
        if not m:
            continue
        label, idx_text = m.group(1).strip(), m.group(2).strip()
        per_stage[label] = {int(x) for x in idx_text.split(',') if x.strip().lstrip('-').isdigit()}
    if any(label not in per_stage for label in stage_labels):
        return []
    common = set.intersection(*(per_stage[label] for label in stage_labels))
    return sorted(common, key=lambda d: (d != 0, d))


def configure_condition(h, client_id: str, ptype: str, meta_key: str, indices: str, value: str) -> None:
    """Set the predicate that decides which detections are passed to the conditional tertiary stage.

    The predicate name is left at its default.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        ptype (str): Predicate type, e.g. 'kpts_conf_gt'.
        meta_key (str): Metadata key the predicate reads.
        indices (str): Comma-separated keypoint indices.
        value (str): Confidence threshold.
    """
    time.sleep(0.3)
    h['set_field'](client_id, 'type', ptype)
    h['set_field'](client_id, 'predicate meta_key', meta_key)
    h['set_field'](client_id, 'indices (comma-separated, e.g. 0,1,2)', indices)
    h['set_field'](client_id, 'value (confidence threshold)', value)
    log(f'PASS: condition set to {ptype}(meta_key={meta_key}, indices={indices}, value={value}) '
        '(predicate name left at its default "roi_gate")')


def run_health_check(h, client_id: str, health_timeout_s: float = 240.0) -> str:
    """Set the imdecode override and class filter, run the health check for all models and wait for all three stages to report.

    Ends the test through `die` if the check reports a failure, does not finish in time, or a stage has 0 healthy devices.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        health_timeout_s (float, optional): Seconds to wait for the result. Defaults to 240.0.

    Returns:
        str: The health check text, one line per stage.
    """
    h['set_field'](client_id, 'imdecode_threads override', IMDECODE_THREADS_OVERRIDE)
    log(f'PASS: imdecode_threads override set to {IMDECODE_THREADS_OVERRIDE}')
    h['set_field'](client_id, 'classes (optional', FILTER_CLASSES, required=False)
    log(f'PASS: filter classes set to {FILTER_CLASSES!r}')

    log('clicking Run Health Check (all models)')
    h['click'](client_id, 'Run Health Check (all models)')
    deadline = time.time() + health_timeout_s
    last_text = ''
    healthy_lines = 0
    while time.time() < deadline:
        text = h['get_text'](client_id, 'device(s) healthy')
        if text:
            last_text = text
            healthy_lines = len([l for l in text.split('\n') if l.strip()])
            if healthy_lines >= 3 and 'Checking' not in text:
                break
        failed_text = h['get_text'](client_id, 'health check failed')
        if failed_text:
            die(f'health check failed: {failed_text}')
        time.sleep(2.0)
    if healthy_lines < 3 or 'Checking' in last_text:
        die(f'health check never reported all 3 stages within {health_timeout_s}s (last seen: {last_text!r})')
    log(f'PASS: health check -- all 3 stages report healthy device(s):\n{last_text}')
    for line in last_text.split('\n'):
        if 'healthy' in line and '0/' in line.split('healthy')[0].split(':')[-1]:
            die(f'health check reported 0 healthy devices for a stage: {line}')
    return last_text


def generate_pipeline(h, client_id: str) -> None:
    """Press Generate Pipeline and wait for the Three-Stage Conditional Cascade dialog to close.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('clicking Generate Pipeline')
    h['click'](client_id, 'Generate Pipeline')
    if not h['wait_dialog'](client_id, False, timeout_s=15.0):
        die('Three-Stage Conditional Cascade dialog never closed after Generate Pipeline')
    time.sleep(1.0)
    log('PASS: Generate Pipeline closed the dialog')


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

    Makes up to three attempts. A busy-device notification triggers Force Stop All and a retry. An OpenCL driver error triggers one retry after disabling OpenCL and regenerating the config YAML. A device fault is reported to the caller instead of ending the test.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for an outcome per attempt. Defaults to 900.0.

    Returns:
        str: The value of the 'Inference endpoint(s)' field ('' if empty), or the string 'device_fault' if the device faulted.
    """
    opencl_error_signatures = ('OpenCL platform',)

    def try_compile() -> tuple[str, int]:
        """Click the compile button and watch notifications and the button state until an outcome is known.

        Returns:
            tuple[str, int]: Outcome ('launched', 'device_busy', 'device_fault', 'opencl_error', 'reenabled', 'timeout' or 'button_not_found') and the notification id seen before the click.
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
            if h['notifications_mention'](client_id, since_id, DEVICE_FAULT_SIGNATURES):
                return 'device_fault', since_id
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
        if outcome == 'device_fault':
            result = 'device_fault'
            break
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
    if result == 'device_fault':
        log(f'device fault detected during compile/launch: {notif_texts}')
        return 'device_fault'
    if result != 'ok':
        die(f'compile/launch did not succeed (result={result}); recent notifications: {notif_texts}')
    endpoint = h['get_field_value'](client_id, 'Inference endpoint(s)')
    log(f'PASS: compile/launch succeeded -- endpoint(s): {endpoint!r} (recent notifications: {notif_texts})')
    return endpoint or ''


def read_raw_infer_fps(h, client_id: str, source_id: str) -> float | None:
    """Return the `infer_fps` metric of a benchmark source from the UI state, or None if it has not been reported."""
    metrics = h['get_state'](client_id).get('sources', {}).get(source_id, {})
    return metrics.get('infer_fps')


def assert_fps_stable_retry(h, client_id: str, source_id: str, floor_fps: float, ceiling_fps: float, *,
                             settle_s: float, hold_s: float, sample_interval_s: float, max_retries: int,
                             hold_growth: float, label: str) -> float:
    """Check that the measured inference fps of a source stays inside a band for a whole hold period.

    Samples the source's `infer_fps` every `sample_interval_s` for the hold time after a settle delay. A hold that has a missing sample or an out-of-band sample is retried with the hold multiplied by `hold_growth`, up to `max_retries` retries.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session.
        source_id (str): Id of the benchmark source in the UI state.
        floor_fps (float): Lowest acceptable sample.
        ceiling_fps (float): Highest acceptable sample.
        settle_s (float): Seconds to wait before each sampling window.
        hold_s (float): Length of the first sampling window in seconds.
        sample_interval_s (float): Seconds between samples.
        max_retries (int): Number of extra windows after the first failure.
        hold_growth (float): Factor applied to the window on each retry.
        label (str): Tag used in log and error messages.

    Returns:
        float: Mean of the samples in the passing window.

    Raises:
        RuntimeError: If the last window still has missing or out-of-band samples.
    """
    attempt_hold = hold_s
    for attempt in range(max_retries + 1):
        time.sleep(settle_s)
        samples: list[float | None] = []
        t0 = time.time()
        while time.time() - t0 < attempt_hold:
            time.sleep(sample_interval_s)
            raw = read_raw_infer_fps(h, client_id, source_id)
            samples.append(raw)
            log(f'  [{label}] t+{time.time() - t0:4.1f}s raw_infer_fps={raw}')
        missing = sum(1 for s in samples if s is None)
        valid = [s for s in samples if s is not None]
        bad = [s for s in valid if s < floor_fps or s > ceiling_fps]
        if not missing and not bad:
            mean = sum(valid) / len(valid)
            log(f'PASS: {label} stable across {attempt_hold:.0f}s -- {len(valid)}/{len(valid)} samples '
                f'>= {floor_fps:.1f}, <= {ceiling_fps:.1f} (mean={mean:.1f})')
            return mean
        if attempt < max_retries:
            log(f'WARNING: {label} not stable within a {attempt_hold:.0f}s hold (missing={missing}, '
                f'bad={len(bad)}/{len(valid) or 1}) -- retrying with a longer '
                f'{attempt_hold * hold_growth:.0f}s hold')
            attempt_hold *= hold_growth
            continue
        if missing:
            raise RuntimeError(f'{label}: {missing}/{len(samples)} samples had no infer_fps reading at all')
        mean = sum(valid) / len(valid)
        raise RuntimeError(f'{label}: NOT stable -- {len(bad)}/{len(valid)} samples violated '
                            f'[{floor_fps:.1f}, {ceiling_fps:.1f}] (mean={mean:.1f}, samples={valid})')
    raise AssertionError('unreachable')


def assert_fps_mean_stable(h, client_id: str, source_id: str, target_fps: float, *,
                            tolerance_frac: float = 0.05, min_samples: int = 500, settle_s: float = 2.0,
                            sample_interval_s: float = 0.2, label: str | None = None) -> float:
    """Check that the mean measured inference fps of a source is within a tolerance of the target.

    After a settle delay, collects `min_samples` readings of `infer_fps` at `sample_interval_s` spacing and compares the mean of the valid ones with the target.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session.
        source_id (str): Id of the benchmark source in the UI state.
        target_fps (float): Expected average fps.
        tolerance_frac (float, optional): Allowed relative deviation. Defaults to 0.05.
        min_samples (int, optional): Number of readings to collect. Defaults to 500.
        settle_s (float, optional): Seconds to wait before sampling. Defaults to 2.0.
        sample_interval_s (float, optional): Seconds between readings. Defaults to 0.2.
        label (str | None, optional): Tag for messages. Defaults to '<target> fps (mean-gated)'.

    Returns:
        float: The mean fps.

    Raises:
        RuntimeError: If no reading is valid or the mean is outside the tolerance band.
    """
    label = label or f'{target_fps:.0f} fps (mean-gated)'
    time.sleep(settle_s)
    samples: list[float | None] = []
    t0 = time.time()
    while len(samples) < min_samples:
        raw = read_raw_infer_fps(h, client_id, source_id)
        samples.append(raw)
        time.sleep(sample_interval_s)
    elapsed = time.time() - t0
    missing = sum(1 for s in samples if s is None)
    valid = [s for s in samples if s is not None]
    if not valid:
        raise RuntimeError(f'{label}: all {len(samples)} samples had no infer_fps reading at all')
    mean = sum(valid) / len(valid)
    lo, hi = target_fps * (1 - tolerance_frac), target_fps * (1 + tolerance_frac)
    if not (lo <= mean <= hi):
        raise RuntimeError(
            f'{label}: mean {mean:.2f} over {len(valid)}/{len(samples)} samples (collected in '
            f'{elapsed:.0f}s) is outside [{lo:.1f}, {hi:.1f}]')
    log(f'PASS: {label} mean {mean:.2f} fps over {len(valid)}/{len(samples)} samples '
        f'(collected in {elapsed:.0f}s, missing={missing}) within [{lo:.1f}, {hi:.1f}]')
    return mean


def run_benchmark_tab_sweep(h, client_id: str) -> list[str]:
    """Add an image source on the Benchmarking tab and step its target fps through FPS_STEPS, gating each step.

    Clears old sources, disables AIMD backoff, sets the backpressure cap and adds the image at the first step's fps. Every step but the last must hold its fps within the tolerance band for the hold period; the last step is gated on its mean fps over many samples. A step failure is recorded and the sweep continues. The source is removed at the end.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.

    Returns:
        list[str]: One message per failed step, empty if all steps passed.
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

    log(f'clicking Add file -> {BENCHMARK_IMAGE_FILENAME} at {FPS_STEPS[0]} FPS')
    h['click'](client_id, 'Add file')
    if not h['wait_dialog'](client_id, True, timeout_s=5.0):
        die('Add file dialog never opened')
    h['set_field'](client_id, 'File / folder', BENCHMARK_IMAGE_FILENAME)
    h['set_field'](client_id, 'FPS', str(FPS_STEPS[0]))
    h['click'](client_id, 'Open')
    if not h['wait_dialog'](client_id, False, timeout_s=5.0):
        die('Add file dialog never closed after Open')
    log(f'PASS: added image source {BENCHMARK_IMAGE_FILENAME!r} at {FPS_STEPS[0]} FPS')

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

    failures: list[str] = []
    for i, target in enumerate(FPS_STEPS):
        if i > 0:
            log(f'retargeting live source to {target} FPS')
            h['set_field'](client_id, f'Target FPS: {BENCHMARK_IMAGE_FILENAME}', str(target), required=False)
        is_ceiling = target == max(FPS_STEPS)
        label = f'{target} FPS step' + (' (sweep ceiling -- must stay stable)' if is_ceiling else '')
        try:
            if is_ceiling:
                log(f'performance gate (mean-gated): after a {FPS_GATE_SETTLE_S:.0f}s settle, sampling raw '
                    f'infer_fps until >=500 readings are collected to confirm the pipeline SUSTAINS '
                    f'{target} FPS on average, not just per-sample')
                assert_fps_mean_stable(h, client_id, new_source_id, target, settle_s=FPS_GATE_SETTLE_S,
                                        label=label)
            else:
                log(f'performance gate: after a {FPS_GATE_SETTLE_S:.0f}s settle, sampling raw infer_fps every '
                    f'{FPS_GATE_SAMPLE_INTERVAL_S:.0f}s for ~{FPS_GATE_HOLD_S:.0f}s (longer on retry) to confirm the '
                    f'pipeline SUSTAINS {target} FPS, not just touches it once')
                assert_fps_stable_retry(
                    h, client_id, new_source_id, target * (1 - FPS_GATE_TOLERANCE_FRAC),
                    target * (1 + FPS_GATE_TOLERANCE_FRAC), settle_s=FPS_GATE_SETTLE_S, hold_s=FPS_GATE_HOLD_S,
                    sample_interval_s=FPS_GATE_SAMPLE_INTERVAL_S, max_retries=FPS_GATE_MAX_RETRIES,
                    hold_growth=FPS_GATE_HOLD_GROWTH, label=label)
        except RuntimeError as exc:
            failures.append(str(exc))
            log(f'FAIL: {exc}')

    log('cleaning up: removing the benchmark source so it does not contend with later runs')
    h['click'](client_id, 'delete_sweep')
    time.sleep(0.5)
    log('PASS: removed benchmark source(s) (cleanup)')
    return failures


def run(h, client_id: str) -> list[str]:
    """Run the whole Three-Stage Conditional Cascade workflow in one browser session.

    Configures the stages, runs the health check and tries each candidate device in order until one compiles without a device fault, then runs the benchmark sweep.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.

    Returns:
        list[str]: Failure messages from the benchmark sweep (empty on success). Other failures end the test through `die`.
    """
    def configure_stages() -> None:
        """Configure every stage of the wizard and the tertiary stage's condition with the module settings."""
        configure_stage(h, client_id, 'Primary model', PRIMARY_MODEL, PRIMARY_CORES, 'det')
        configure_stage(h, client_id, 'Secondary model', SECONDARY_MODEL, SECONDARY_CORES, 'pose')
        configure_stage(h, client_id, 'Conditional tertiary model', TERTIARY_MODEL, TERTIARY_CORES, 'face')
        configure_condition(h, client_id, PREDICATE_TYPE, PREDICATE_META_KEY, PREDICATE_INDICES, PREDICATE_VALUE)

    force_stop_all(h, client_id)
    open_three_stage_cascade_wizard(h, client_id)
    configure_stages()
    health_text = run_health_check(h, client_id)
    candidates = healthy_device_candidates(health_text, STAGE_LABELS)
    if not candidates:
        die(f'no single device is healthy for every stage of this cascade -- not a go:\n{health_text}')
    log(f'PASS: candidate device(s) to try, in order: {candidates}')

    tried: list[int] = []
    outcome = 'device_fault'
    for i, device in enumerate(candidates):
        tried.append(device)
        if i > 0:
            force_stop_all(h, client_id)
            open_three_stage_cascade_wizard(h, client_id)
            configure_stages()
        if device != 0:
            select_device(h, client_id, 'Primary model', device, PRIMARY_CORES)
            select_device(h, client_id, 'Secondary model', device, SECONDARY_CORES)
            select_device(h, client_id, 'Conditional tertiary model', device, TERTIARY_CORES)
        generate_pipeline(h, client_id)
        ensure_opencl_disabled(h, client_id)
        generate_config_yaml(h, client_id)
        outcome = compile_and_launch_vision(h, client_id)
        if outcome != 'device_fault':
            break
        log(f'device {device} faulted at compile time -- '
            f'{len(candidates) - len(tried)} candidate(s) left to try')
    if outcome == 'device_fault':
        die(f'every candidate device faulted at compile time: {tried}')

    failures = run_benchmark_tab_sweep(h, client_id)
    log('ALL DONE -- fastapi-driven Three-Stage Conditional Cascade release workflow finished')
    return failures


def main() -> int:
    """Prepare the host, run the workflow in a fresh or existing browser session, and print a summary.

    Without `--client-id` a headless Chromium tab is opened and its console and page errors are recorded. With `--client-id` the test attaches to that live session and records none.

    Returns:
        int: 0 if the sweep had no failures and there were no console or page errors, 1 otherwise (`die` exits earlier with 1).
    """
    prepare_host([PRIMARY_MODEL, SECONDARY_MODEL, TERTIARY_MODEL])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8090')
    parser.add_argument('--client-id', default=None)
    args = parser.parse_args()

    h = make_agent_helpers(args.base_url)
    failures: list[str] = []

    if args.client_id:
        log(f'attaching to existing live client_id={args.client_id} -- no new browser tab, '
            'no console/page-error capture')
        failures = run(h, args.client_id)
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
                failures = run(h, client_id)
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
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
    ok = not (failures or console_errors or page_errors)
    print('test_release_fastapi_cascade3: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
