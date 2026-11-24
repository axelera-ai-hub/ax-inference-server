#!/usr/bin/env python3

"""Ad-hoc end-to-end test of the Three-Stage Conditional Cascade workflow as a user would drive it, through the Pipeline Editor's `/_agent` HTTP API.

Configures the three stages and the condition, health checks, generates and launches the pipeline, then adds an image source on the Benchmarking tab with an optional AxMonitor trace. Usage: test_release_fastapi_cascade3_e2e_user_workflow.py [base_url] [--client-id ID].
"""

from __future__ import annotations

import argparse
import re
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

from utils.axmonitor_trace import AxMonitorTracer
from utils.host_server_prep import prepare_host

PRIMARY_MODEL = 'yolox-m-coco-onnx'
SECONDARY_MODEL = 'yolo26npose-coco-onnx'
TERTIARY_MODEL = 'retinaface-mobilenet0.25-widerface-onnx'
PRIMARY_CORES = '1'
SECONDARY_CORES = '2'
TERTIARY_CORES = '1'
PREDICATE_TYPE = 'kpts_conf_gt'
PREDICATE_META_KEY = 'pose'
PREDICATE_INDICES = '0,1,2'
PREDICATE_VALUE = '0.5'
FILTER_CLASSES = '0'
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
# Source fps requested for the image added on the Benchmarking tab.
BENCHMARK_FPS = '50'

# Matches the notification shown after a successful launch.
LAUNCH_SUCCESS_RE = re.compile(r'Launched \d+ pipeline')
# Notification substrings that mean the device or port is still held by a previous run.
DEVICE_BUSY_SIGNATURES = ('allocate AI cores', 'axr_device_connect', 'Address already in use',
                           'a device health check is currently using')
# Notification substrings that mean the device faulted while compiling or launching.
DEVICE_FAULT_SIGNATURES = ('faulty device(s) detected', 'ZE_RESULT_ERROR_DEVICE_LOST')
# Wizard section labels, which are also the prefixes of the health check lines.
STAGE_LABELS = ['Primary model', 'Secondary model', 'Conditional tertiary model']

# Browser console errors and uncaught page errors collected while the run is driven by Playwright.
console_errors: list[str] = []
page_errors: list[str] = []


def log(msg: str) -> None:
    """Print a message prefixed with the local time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def make_agent_helpers(base_url: str):
    """Create the agent-API helper callables bound to one app server.

    Every helper takes the `client_id` of a live browser session as its first argument. Unlike the other release tests, a rejected call with `required=True` is appended to the shared failures list and printed instead of ending the run.

    Args:
        base_url (str): Base URL of the app, e.g. http://127.0.0.1:8080.

    Returns:
        dict: Name to callable map (click, set_field, get_state, toggle_dropdown, read_dropdown_options, get_field_value, get_text, wait_dialog, notifications_since, notifications_match, max_notif_id, wait_for_new_client_id), the shared httpx client under 'agent', and the failure message list under 'failures'.
    """
    agent = httpx.Client(base_url=base_url, timeout=20.0)
    failures: list[str] = []

    def click(client_id: str, text: str, *, required: bool = True) -> dict:
        """Click the first control whose text matches, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            text (str): Text of the control to click.
            required (bool, optional): If True, record a failure when the click is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/click`.
        """
        r = agent.post('/_agent/click', json={'client_id': client_id, 'text': text}).json()
        if required and not r.get('ok'):
            failures.append(f'click({text!r}) failed: {r}')
            print(f'FAIL: click({text!r}): {r}')
        return r

    def set_field(client_id: str, label: str, value: str, *, required: bool = True) -> dict:
        """Set a form field located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the field.
            value (str): Value to set.
            required (bool, optional): If True, record a failure when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/set_field`.
        """
        r = agent.post('/_agent/set_field', json={'client_id': client_id, 'label': label, 'value': value}).json()
        if required and not r.get('ok'):
            failures.append(f'set_field({label}={value}) failed: {r}')
            print(f'FAIL: set_field({label}={value}): {r}')
        return r

    def toggle_dropdown(client_id: str, label: str, *, required: bool = True) -> dict:
        """Open or close a dropdown located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the dropdown.
            required (bool, optional): If True, record a failure when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/toggle_dropdown`.
        """
        r = agent.post('/_agent/toggle_dropdown', json={'client_id': client_id, 'label': label}).json()
        if required and not r.get('ok'):
            failures.append(f'toggle_dropdown({label!r}) failed: {r}')
            print(f'FAIL: toggle_dropdown({label!r}): {r}')
        return r

    def read_dropdown_options(client_id: str, label: str, *, required: bool = True) -> dict:
        """Read the options of a dropdown located by label, through the app's agent API.

        Args:
            client_id (str): Live browser session to drive.
            label (str): Label of the dropdown.
            required (bool, optional): If True, record a failure when the call is not acknowledged. Defaults to True.

        Returns:
            dict: The JSON response of `POST /_agent/read_dropdown_options`; its `options` list holds dicts with `text` and `selected`.
        """
        r = agent.post('/_agent/read_dropdown_options', json={'client_id': client_id, 'label': label}).json()
        if required and not r.get('ok'):
            failures.append(f'read_dropdown_options({label!r}) failed: {r}')
            print(f'FAIL: read_dropdown_options({label!r}): {r}')
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

    def notifications_match(client_id: str, since_id: int, pattern: re.Pattern) -> bool:
        """Return True if the joined notification text after `since_id` matches the regex."""
        texts = ' '.join(n['message'] for n in notifications_since(client_id, since_id))
        return pattern.search(texts) is not None

    def max_notif_id(client_id: str) -> int:
        """Return the highest notification id of a session, or 0 if it has none."""
        notifs = notifications_since(client_id, 0)
        return max((n['id'] for n in notifs), default=0)

    def wait_for_new_client_id(before: set[str], timeout_s: float = 10.0) -> str | None:
        """Wait for a browser session that was not in `before` to open its socket connection.

        Args:
            before (set[str]): Client ids that were already live.
            timeout_s (float, optional): Maximum wait in seconds. Defaults to 10.0.

        Returns:
            str | None: The id of a newly connected session, or None on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            sessions = agent.get('/_agent/sessions').json().get('sessions', [])
            live_ids = {s['client_id'] for s in sessions if s.get('has_socket_connection')}
            fresh = live_ids - before
            if fresh:
                return next(iter(fresh))
            time.sleep(0.2)
        return None

    return {
        'agent': agent, 'click': click, 'set_field': set_field, 'get_state': get_state,
        'toggle_dropdown': toggle_dropdown, 'read_dropdown_options': read_dropdown_options,
        'get_field_value': get_field_value, 'get_text': get_text, 'wait_dialog': wait_dialog,
        'notifications_since': notifications_since, 'notifications_match': notifications_match,
        'max_notif_id': max_notif_id, 'wait_for_new_client_id': wait_for_new_client_id, 'failures': failures,
    }


def force_stop_all(h, client_id: str) -> None:
    """Open the Pipeline Editor tab and press Force Stop All, confirming the dialog if one appears.

    None of the clicks is required, so a missing button is not recorded as a failure.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('clicking Pipeline Editor tab')
    h['click'](client_id, 'Pipeline Editor', required=False)
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
    time.sleep(1.5)
    log('PASS: force stop all')


def configure_stage(h, client_id: str, stage_label: str, model_name: str, cores: str, meta_key: str,
                     download_timeout_s: float = 300.0) -> None:
    """Configure one wizard stage: model, meta key override and cores on Device 0.

    Opens the stage's section (except the primary one) and selects the model from the host-server build dropdown. If that fails it enables 'Use prebuilt models', selects the model from the catalog and waits for its download. On a failure the message is recorded in the failures list and the function returns without finishing the stage.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        stage_label (str): Section label, e.g. 'Primary model'.
        model_name (str): Model to select.
        cores (str): Number of cores on Device 0.
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
            h['failures'].append(f'{stage_label}: could not enable "Use prebuilt models": {toggle_r}')
            print(f'FAIL: {stage_label}: could not enable "Use prebuilt models": {toggle_r}')
            return

        deadline = time.time() + 60.0
        prebuilt_r: dict = {}
        while time.time() < deadline:
            prebuilt_r = h['set_field'](client_id, 'Prebuilt model (axdownloadmodel catalog)', model_name,
                                         required=False)
            if prebuilt_r.get('ok') or prebuilt_r.get('error') == 'option_not_found':
                break
            time.sleep(1.0)
        if not prebuilt_r.get('ok'):
            h['failures'].append(f'{stage_label}: {model_name!r} not found in the prebuilt catalog: {prebuilt_r}')
            print(f'FAIL: {stage_label}: {model_name!r} not found in the prebuilt catalog: {prebuilt_r}')
            return
        log(f'{stage_label}: selected {model_name!r} from the prebuilt catalog -- '
            'waiting for its artifacts to download')

        deadline = time.time() + download_timeout_s
        downloaded = False
        while time.time() < deadline:
            notif_texts = ' '.join(n['message'] for n in h['notifications_since'](client_id, 0))
            if model_name in notif_texts and ('failed' in notif_texts.lower()
                                               or 'could not reach' in notif_texts.lower()):
                h['failures'].append(f'failed to download prebuilt model {model_name!r}: {notif_texts}')
                print(f'FAIL: failed to download prebuilt model {model_name!r}: {notif_texts}')
                return
            current = h['get_field_value'](client_id, 'Prebuilt model (axdownloadmodel catalog)') or ''
            if model_name in current and 'downloaded' in current.lower():
                downloaded = True
                break
            time.sleep(1.0)
        if not downloaded:
            h['failures'].append(f'prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')
            print(f'FAIL: prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')
            return
        log(f'PASS: {stage_label}: {model_name!r} downloaded')
    h['set_field'](client_id, 'meta_key_override', meta_key)
    cores_r = h['set_field'](client_id, 'Cores on Device 0', cores, required=False)
    if not cores_r.get('ok'):
        h['failures'].append(f'{stage_label}: could not set cores on Device 0 to {cores}: {cores_r}')
        print(f'FAIL: {stage_label}: could not set cores on Device 0 to {cores}: {cores_r}')
        return
    log(f'PASS: {stage_label} set to {model_name}, Device 0, {cores} core(s), meta_key_override={meta_key}')


def select_device(h, client_id: str, stage_label: str, device: int, cores: str) -> bool:
    """Move one wizard stage from Device 0 to another device and set its cores there.

    Opens the stage's Devices dropdown, deselects any other selected device, selects the target one and sets 'Cores on Device <device>'.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        stage_label (str): Section label of the stage.
        device (int): Index of the device to use.
        cores (str): Number of cores on that device.

    Returns:
        bool: True if the device and cores were set, False after recording a failure.
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
        msg = f'{stage_label}: device {device} not found among dropdown options: {[o.get("text") for o in options]}'
        h['failures'].append(msg)
        print(f'FAIL: {msg}')
        return False
    if not already_selected:
        r = h['set_field'](client_id, label, target_text)
        if not r.get('ok'):
            h['failures'].append(f'{stage_label}: could not select device {device}: {r}')
            print(f'FAIL: {stage_label}: could not select device {device}: {r}')
            return False
    close_r = h['toggle_dropdown'](client_id, label, required=False)
    if close_r.get('is_open'):
        h['toggle_dropdown'](client_id, label, required=False)
    cores_r = h['set_field'](client_id, f'Cores on Device {device}', cores, required=False)
    if not cores_r.get('ok'):
        h['failures'].append(f'{stage_label}: could not set cores on device {device} to {cores}: {cores_r}')
        print(f'FAIL: {stage_label}: could not set cores on device {device} to {cores}: {cores_r}')
        return False
    log(f'PASS: {stage_label} moved to device {device}, {cores} core(s)')
    return True


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


def run_health_check(h, client_id: str, health_timeout_s: float = 240.0) -> str | None:
    """Set the class filter, run the health check for all models and wait for all three stages to report.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        health_timeout_s (float, optional): Seconds to wait for the result. Defaults to 240.0.

    Returns:
        str | None: The health check text, one line per stage (a failure is recorded if a stage is missing or has 0 healthy devices), or None if a busy-device notification appeared so the caller can retry.
    """

    h['set_field'](client_id, 'classes (optional', FILTER_CLASSES, required=False)
    log(f'PASS: filter classes set to {FILTER_CLASSES!r}')

    since_id = h['max_notif_id'](client_id)
    log('clicking Run Health Check (all models)')
    h['click'](client_id, 'Run Health Check (all models)')
    deadline = time.time() + health_timeout_s
    last_text = ''
    healthy_lines = 0
    while time.time() < deadline:
        if _notifications_mention(h, client_id, since_id, DEVICE_BUSY_SIGNATURES):
            log('device busy (health check lock not yet released)')
            return None
        text = h['get_text'](client_id, 'device(s) healthy')
        if text:
            last_text = text
            healthy_lines = len([l for l in text.split('\n') if l.strip()])
            if healthy_lines >= 3 and 'Checking' not in text:
                break
        failed_text = h['get_text'](client_id, 'health check failed')
        if failed_text:
            h['failures'].append(f'health check failed: {failed_text}')
            print(f'FAIL: health check failed: {failed_text}')
            return last_text
        time.sleep(2.0)
    if healthy_lines < 3 or re.search(r'(?<!\d)0/\d+ device\(s\) healthy', last_text):
        h['failures'].append(f'health check did not report all 3 stages healthy within {health_timeout_s}s: '
                              f'{last_text!r}')
        print(f'FAIL: health check result:\n{last_text}')
    else:
        log(f'PASS: health check -- all 3 stages report healthy device(s):\n{last_text}')
    return last_text


def generate_pipeline(h, client_id: str) -> None:
    """Press Generate Pipeline and wait for the Three-Stage Conditional Cascade dialog to close, recording a failure if it stays open.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('clicking Generate Pipeline')
    h['click'](client_id, 'Generate Pipeline')
    if not h['wait_dialog'](client_id, False, timeout_s=15.0):
        h['failures'].append('Three-Stage Conditional Cascade dialog never closed after Generate Pipeline')
        print('FAIL: dialog still open after Generate Pipeline click')
        return
    time.sleep(1.0)
    log('PASS: Generate Pipeline closed the dialog')


def ensure_opencl_disabled(h, client_id: str) -> None:
    """Turn the OpenCL global setting off, recording a failure if the field cannot be set.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
    """
    log('disabling OpenCL in Global Settings')
    r = h['set_field'](client_id, 'OpenCL', 'false', required=False)
    if not r.get('ok'):
        h['failures'].append(f'could not disable OpenCL: {r}')
        print(f'FAIL: could not disable OpenCL: {r}')
        return
    log('PASS: OpenCL global setting disabled')


def generate_config_yaml(h, client_id: str, timeout_s: float = 30.0) -> None:
    """Press Generate Config YAML, save the preview dialog, and wait for the 'Wrote ...' notification.

    Each step that does not happen is recorded as a failure and ends the function.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for the notification after saving. Defaults to 30.0.
    """
    log('generating config YAML')
    if not h['click'](client_id, 'Generate Config YAML', required=False).get('ok'):
        h['failures'].append('Generate Config YAML button click failed')
        print('FAIL: Generate Config YAML button click failed')
        return
    if not h['wait_dialog'](client_id, True):
        h['failures'].append('YAML preview dialog never opened')
        print('FAIL: YAML preview dialog never opened')
        return
    h['click'](client_id, 'Save')
    if not h['wait_dialog'](client_id, False):
        h['failures'].append('YAML preview dialog never closed')
        print('FAIL: YAML preview dialog never closed')
        return
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
        h['failures'].append('Generate Config YAML -> Save never produced a "Wrote ..." notification')
        print('FAIL: no "Wrote ..." notification seen')
        return
    log(f'PASS: {wrote_text}')


def _notifications_mention(h, client_id: str, since_id: int, signatures: tuple[str, ...]) -> bool:
    """Return True if any notification after `since_id` contains one of the given substrings."""
    texts = ' '.join(n['message'] for n in h['notifications_since'](client_id, since_id))
    return any(sig in texts for sig in signatures)


def compile_and_launch(h, client_id: str, timeout_s: float = 240.0) -> str:
    """Press Compile and Launch Pipeline and decide the outcome from the notifications that follow.

    Makes up to three attempts. A busy-device notification triggers Force Stop All and a retry. An OpenCL driver error triggers one retry after disabling OpenCL and regenerating the config YAML. A negative notification is recorded as a failure. Success is tentative: it only means no negative notification was seen.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        timeout_s (float, optional): Seconds to wait for an outcome per attempt. Defaults to 240.0.

    Returns:
        str: 'ok', 'device_fault' (the caller may try another device), or 'failed'.
    """

    opencl_error_signatures = ('OpenCL platform',)
    opencl_retried = False
    for attempt in range(3):
        since_id = h['max_notif_id'](client_id)
        log('clicking Compile and Launch Pipeline')
        if not h['click'](client_id, 'Compile and Launch Pipeline', required=False).get('ok'):
            h['failures'].append('Compile and Launch Pipeline button click failed')
            print('FAIL: Compile and Launch Pipeline button click failed')
            return 'failed'
        deadline = time.time() + timeout_s
        negative_seen = False
        device_busy = False
        device_fault = False
        opencl_error = False
        while time.time() < deadline:
            notifs = h['notifications_since'](client_id, since_id)
            for n in notifs:
                if n.get('type') == 'negative':
                    negative_seen = True
            if _notifications_mention(h, client_id, since_id, DEVICE_BUSY_SIGNATURES):
                device_busy = True
                break
            if _notifications_mention(h, client_id, since_id, DEVICE_FAULT_SIGNATURES):
                device_fault = True
                break
            if _notifications_mention(h, client_id, since_id, opencl_error_signatures):
                opencl_error = True
                break
            if h['notifications_match'](client_id, since_id, LAUNCH_SUCCESS_RE):
                break
            if any(w in (n['message'] or '').lower() for n in notifs for w in ('launch', 'compiled', 'running')):
                break
            time.sleep(3.0)
        if device_fault:
            texts = [n['message'] for n in h['notifications_since'](client_id, since_id)]
            log(f'device fault detected during compile/launch: {texts}')
            return 'device_fault'
        if device_busy and attempt < 2:
            log('device busy (health check lock not yet released) -- Force Stop All and retrying')
            force_stop_all(h, client_id)
            continue
        if opencl_error and not opencl_retried:
            log('OpenCL driver error -- disabling OpenCL and regenerating config YAML before retrying')
            ensure_opencl_disabled(h, client_id)
            generate_config_yaml(h, client_id)
            opencl_retried = True
            continue
        if negative_seen:
            texts = [n['message'] for n in h['notifications_since'](client_id, since_id)]
            h['failures'].append(f'Compile and Launch Pipeline raised a negative notification: {texts}')
            print(f'FAIL: negative notification seen during compile/launch: {texts}')
            return 'failed'
        log('PASS (tentative): no negative notification seen during compile/launch')
        return 'ok'
    return 'failed'


def run_benchmark_add_and_trace(h, client_id: str, base_url: str) -> None:
    """Add an image source on the Benchmarking tab and sample AxMonitor stats while it runs.

    The trace is active only when AXMONITOR_TRACE=1 is set. Missing or all-zero utilization is printed as a warning and does not fail the test. The source is removed at the end.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        base_url (str): App base URL, passed to the tracer to derive the host server URL.
    """
    log('clicking Benchmarking tab')
    h['click'](client_id, 'Benchmarking')
    time.sleep(0.5)

    tracer = AxMonitorTracer(base_url)
    if tracer.error:
        log(f'WARNING: {tracer.error}')

    log(f'clicking Add file -> {BENCHMARK_IMAGE_FILENAME} at {BENCHMARK_FPS} FPS')
    h['click'](client_id, 'Add file')
    if not h['wait_dialog'](client_id, True, timeout_s=5.0):
        h['failures'].append('Add file dialog never opened')
        print('FAIL: Add file dialog never opened')
        return
    h['set_field'](client_id, 'File / folder', BENCHMARK_IMAGE_FILENAME)
    h['set_field'](client_id, 'FPS', BENCHMARK_FPS)
    h['click'](client_id, 'Open')
    if not h['wait_dialog'](client_id, False, timeout_s=5.0):
        h['failures'].append('Add file dialog never closed after Open')
        print('FAIL: Add file dialog never closed after Open')
        return
    tracer.start()
    time.sleep(3.0)
    log(f'PASS: added image source {BENCHMARK_IMAGE_FILENAME!r} at {BENCHMARK_FPS} FPS')

    time.sleep(5.0)
    if tracer.enabled:
        time.sleep(10.0)
    tracer.stop()

    trace_summary = tracer.summarize()
    if trace_summary is not None:
        log(f'--- AxMonitor trace summary --- {trace_summary}')
        if trace_summary['error_count'] == trace_summary['sample_count']:
            print(f'WARNING: AxMonitor trace -- all {trace_summary["sample_count"]} poll(s) of /api/v1/monitor/stats failed (not a test failure)')
        elif trace_summary['max_core_utilization_pct'] <= 0 and trace_summary['max_ddr_utilization_pct'] <= 0:
            print(f'WARNING: AxMonitor trace -- core/DDR utilization stayed at 0 across {trace_summary["sample_count"]} samples while frames were streaming (not a test failure)')
        else:
            log('PASS: AxMonitor trace observed non-zero utilization during active benchmark run')

    log('cleaning up: removing the benchmark source')
    h['click'](client_id, 'delete_sweep', required=False)
    time.sleep(0.5)


def run(h, client_id: str, base_url: str) -> list[str]:
    """Run the whole ad-hoc workflow in one browser session.

    Opens the wizard, configures the stages, retries the health check while the device is busy, then tries each candidate device in order until one compiles without a device fault, and finally runs the benchmark step.

    Args:
        h (dict): Helper callables from make_agent_helpers.
        client_id (str): Live browser session to drive.
        base_url (str): App base URL.

    Returns:
        list[str]: The accumulated failure messages, empty on success.
    """
    def open_wizard() -> bool:
        """Force stop everything and open the Three-Stage Conditional Cascade wizard.

        Returns:
            bool: True if the dialog opened, False after recording a failure.
        """
        force_stop_all(h, client_id)
        log('expanding the Examples palette category')
        h['click'](client_id, 'Examples')
        time.sleep(0.3)
        log('clicking "Three-Stage Conditional Cascade"')
        h['click'](client_id, 'Three-Stage Conditional Cascade')
        if not h['wait_dialog'](client_id, True, timeout_s=10.0):
            h['failures'].append('Three-Stage Conditional Cascade dialog never opened')
            print('FAIL: wizard dialog never opened')
            return False
        log('PASS: Three-Stage Conditional Cascade dialog opened')
        return True

    def configure_stages() -> None:
        """Configure the three stages and the tertiary stage's condition with the module settings."""
        configure_stage(h, client_id, 'Primary model', PRIMARY_MODEL, PRIMARY_CORES, 'det')
        configure_stage(h, client_id, 'Secondary model', SECONDARY_MODEL, SECONDARY_CORES, 'pose')
        configure_stage(h, client_id, 'Conditional tertiary model', TERTIARY_MODEL, TERTIARY_CORES, 'face')
        configure_condition(h, client_id, PREDICATE_TYPE, PREDICATE_META_KEY, PREDICATE_INDICES, PREDICATE_VALUE)

    if not open_wizard():
        return h['failures']
    configure_stages()
    health_text = None
    for attempt in range(3):
        health_text = run_health_check(h, client_id)
        if health_text is not None:
            break
        log(f'retrying health check after device-busy (attempt {attempt + 1}/3)')
        if not open_wizard():
            return h['failures']
        configure_stages()
    if health_text is None:
        h['failures'].append('health check never ran -- device busy on every retry attempt')
        print('FAIL: health check device busy on every retry attempt')
        health_text = ''
    candidates = healthy_device_candidates(health_text, STAGE_LABELS)
    if not candidates:
        h['failures'].append(f'no single device is healthy for every stage of this cascade -- not a go:\n{health_text}')
        print(f'FAIL: no device is healthy for every stage:\n{health_text}')
        return h['failures']
    log(f'PASS: candidate device(s) to try, in order: {candidates}')

    tried: list[int] = []
    outcome = 'device_fault'
    for i, device in enumerate(candidates):
        tried.append(device)
        if i > 0:
            if not open_wizard():
                return h['failures']
            configure_stages()
        if device != 0:
            moved = (select_device(h, client_id, 'Primary model', device, PRIMARY_CORES)
                     and select_device(h, client_id, 'Secondary model', device, SECONDARY_CORES)
                     and select_device(h, client_id, 'Conditional tertiary model', device, TERTIARY_CORES))
            if not moved:
                continue
        generate_pipeline(h, client_id)
        ensure_opencl_disabled(h, client_id)
        generate_config_yaml(h, client_id)
        outcome = compile_and_launch(h, client_id)
        if outcome != 'device_fault':
            break
        log(f'device {device} faulted at compile time -- '
            f'{len(candidates) - len(tried)} candidate(s) left to try')
    if outcome == 'device_fault':
        h['failures'].append(f'every candidate device faulted at compile time: {tried}')
        print(f'FAIL: every candidate device faulted at compile time: {tried}')
        return h['failures']

    run_benchmark_add_and_trace(h, client_id, base_url)
    log('ALL DONE -- fastapi-driven ad-hoc Three-Stage Conditional Cascade workflow finished')
    return h['failures']


def main() -> int:
    """Prepare the host, run the workflow in a fresh or existing browser session, and print a summary.

    Without `--client-id` a headless Chromium tab is opened and its console and page errors are recorded. With `--client-id` the test attaches to that live session and records none.

    Returns:
        int: 0 if there were no failures and no console or page errors, 1 otherwise.
    """
    prepare_host([PRIMARY_MODEL, SECONDARY_MODEL, TERTIARY_MODEL])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8080')
    parser.add_argument('--client-id', default=None)
    args = parser.parse_args()

    h = make_agent_helpers(args.base_url)
    failures: list[str] = []

    if args.client_id:
        log(f'attaching to existing live client_id={args.client_id} -- no new browser tab, '
            'no console/page-error capture')
        failures = run(h, args.client_id, args.base_url)
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
            if not client_id:
                print('FAILED -- new Playwright-driven client never registered as a live session')
                print('test_release_fastapi_cascade3_e2e_user_workflow: FAIL')
                return 1
            log(f'using fresh client_id={client_id}')

            try:
                failures = run(h, client_id, args.base_url)
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
    print('test_release_fastapi_cascade3_e2e_user_workflow: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
