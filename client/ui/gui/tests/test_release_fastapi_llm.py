#!/usr/bin/env python3
"""Release test that drives the Iso-VLM/LLM-Demo wizard of a running GUI through its /_agent HTTP API and chats with a qwen3-0.6b vLLM server."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

import httpx
from utils.host_server_prep import prepare_host, require_vllm_artifacts
from playwright.sync_api import sync_playwright

MODEL_NAME = 'qwen3-0.6b'
DEVICE_NAME_OVERRIDE = os.environ.get('VLM_TEST_DEVICE_NAME')
PIPELINE_COUNT = '1'
BASE_PORT = '8001'
NODE_ID = 'vllm-1'
JOKE_PROMPT = 'Tell me a joke.'
FOLLOWUP_PROMPT = 'Why is the sky blue? Answer in two sentences.'
VLLM_LAUNCH_TIMEOUT_S = 300.0
CHAT_REPLY_TIMEOUT_S = 180.0

LAUNCH_SUCCESS_RE = re.compile(r'Launched \d+ vLLM VLM server')
LAUNCH_FAILED_RE = re.compile(r'vLLM launch failed')
_AVG_METRICS_RE = re.compile(r'avg \(last (\d+)\): TTFT ([\d.]+)s\s*\xb7\s*(?:([\d.]+) tok/s|n/a tok/s)')
DEVICE_FAULT_SIGNATURES = ('failed a health check',)


def is_device_fault(text: str) -> bool:
    """Return True if the text contains a known device-fault signature."""
    return any(sig in text for sig in DEVICE_FAULT_SIGNATURES)

console_errors: list[str] = []
page_errors: list[str] = []


def log(msg: str) -> None:
    """Print a message prefixed with the current time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def die(msg: str) -> None:
    """Log a failure, print the test FAIL line and exit.

    Args:
        msg (str): Failure reason.

    Raises:
        SystemExit: Always, with code 1.
    """
    log(f'FAILED -- {msg}')
    print('test_release_fastapi_llm: FAIL')
    sys.exit(1)


def make_agent_helpers(base_url: str):
    """Build the /_agent API helper functions bound to one GUI server.

    Args:
        base_url (str): Base URL of the GUI server.

    Returns:
        dict: Mapping of helper name to callable (agent, click, set_field, hover, get_state, get_field_value,
        get_text, wait_dialog, notifications_since, notifications_match, max_notif_id, wait_for_new_client_id).
        The click, set_field and hover helpers call die() on a failed response unless required=False.
    """
    agent = httpx.Client(base_url=base_url, timeout=20.0)

    def click(client_id: str, text: str, *, required: bool = True) -> dict:
        """Click the element with the given text in a client session and return the JSON response."""
        r = agent.post('/_agent/click', json={'client_id': client_id, 'text': text}).json()
        if required and not r.get('ok'):
            die(f'click({text!r}): {r}')
        return r

    def set_field(client_id: str, label: str, value: str, *, required: bool = True) -> dict:
        """Set the labelled field of a client session to a value and return the JSON response."""
        r = agent.post('/_agent/set_field', json={'client_id': client_id, 'label': label, 'value': value}).json()
        if required and not r.get('ok'):
            die(f'set_field({label}={value}): {r}')
        return r

    def hover(client_id: str, text: str, action: str = 'enter', *, required: bool = True) -> dict:
        """Send a hover action ("enter" or "leave") to the element with the given text and return the JSON response."""
        r = agent.post('/_agent/hover', json={'client_id': client_id, 'text': text, 'action': action}).json()
        if required and not r.get('ok'):
            die(f'hover({text!r}, {action!r}): {r}')
        return r

    def get_state(client_id: str) -> dict:
        """Return the UI state snapshot of a client session."""
        return agent.get('/_agent/state', params={'client_id': client_id}).json()

    def get_field_value(client_id: str, label: str) -> str | None:
        """Return the current value of the field with the given label, or None if there is no such field."""
        for f in get_state(client_id).get('fields', []):
            if (f.get('label') or '') == label:
                return f.get('value')
        return None

    def get_text(client_id: str, contains: str) -> str | None:
        """Return the first text on the page that contains the given string, or None if not found."""
        r = agent.get('/_agent/get_text', params={'client_id': client_id, 'contains': contains}).json()
        return r.get('text') if r.get('ok') else None

    def wait_dialog(client_id: str, present: bool, timeout_s: float = 10.0) -> bool:
        """Poll until a dialog is open (or closed).

        Returns:
            bool: True if the dialog state matched `present` before the timeout, False otherwise.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if get_state(client_id).get('dialog_open') is present:
                return True
            time.sleep(0.15)
        return False

    def notifications_since(client_id: str, since_id: int) -> list[dict]:
        """Return the notifications of a client session whose id is greater than since_id."""
        return agent.get('/_agent/notifications',
                          params={'client_id': client_id, 'since_id': since_id}).json().get('notifications', [])

    def notifications_match(client_id: str, since_id: int, pattern: re.Pattern) -> bool:
        """Return True if the pattern matches the joined text of notifications newer than since_id."""
        texts = ' '.join(n['message'] for n in notifications_since(client_id, since_id))
        return pattern.search(texts) is not None

    def max_notif_id(client_id: str) -> int:
        """Return the highest notification id seen by a client session, or 0 if there are none."""
        notifs = notifications_since(client_id, 0)
        return max((n['id'] for n in notifs), default=0)

    def wait_for_new_client_id(before: set[str], timeout_s: float = 10.0) -> str:
        """Wait for a live client session that was not in the `before` set and return its id.

        Calls die() if none registers within the timeout.
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
        'get_field_value': get_field_value, 'get_text': get_text, 'wait_dialog': wait_dialog,
        'notifications_since': notifications_since, 'notifications_match': notifications_match,
        'max_notif_id': max_notif_id, 'wait_for_new_client_id': wait_for_new_client_id,
    }


def force_stop_all(h, client_id: str) -> None:
    """Open the Pipeline Editor tab and click Force Stop All, confirming the dialog if one appears."""
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


def open_iso_vlm_demo_wizard(h, client_id: str) -> None:
    """Expand the Examples palette category and open the Iso-VLM/LLM-Demo dialog, failing if it does not open within 20 s."""
    log('expanding the Examples palette category')
    h['click'](client_id, 'Examples')
    time.sleep(0.3)
    log('clicking "Iso-VLM/LLM-Demo"')
    h['click'](client_id, 'Iso-VLM/LLM-Demo')
    if not h['wait_dialog'](client_id, True, timeout_s=20.0):
        die('Iso-VLM/LLM-Demo dialog never opened')
    log('PASS: Iso-VLM/LLM-Demo dialog opened')


def discover_device_candidates(h, client_id: str, preferred: str | None) -> tuple[str, list[str]]:
    """Read the options of the wizard Device dropdown and select one.

    The options are discovered by setting a nonexistent device name and reading rendered_options_seen. The
    preferred device is chosen if present, otherwise the first one not marked FAILED HEALTH CHECK.

    Args:
        h (dict): Helpers from make_agent_helpers.
        client_id (str): GUI client session.
        preferred (str | None): Device name to prefer.

    Returns:
        tuple[str, list[str]]: The chosen device and all candidates, chosen first, with unhealthy ones last.
    """
    probe = h['set_field'](client_id, 'Device', '__no_such_device_probe__', required=False)
    names = probe.get('rendered_options_seen') or []
    for _ in range(5):
        if names:
            break
        time.sleep(0.5)
        probe = h['set_field'](client_id, 'Device', '__no_such_device_probe__', required=False)
        names = probe.get('rendered_options_seen') or []
    if not names:
        current = h['get_field_value'](client_id, 'Device')
        if not current:
            die(f'Device dropdown rendered no options and nothing was pre-selected: {probe}')
        return current, [current]
    chosen = preferred if preferred in names else next(
        (n for n in names if 'FAILED HEALTH CHECK' not in n), names[0])
    time.sleep(0.3)
    r = h['set_field'](client_id, 'Device', chosen, required=False)
    if not r.get('ok') and not r.get('rendered_options_seen'):
        time.sleep(0.5)
        r = h['set_field'](client_id, 'Device', chosen, required=False)
    if not r.get('ok'):
        die(f'could not select device {chosen!r} from discovered candidates {names}: {r}')
    candidates = [chosen] + [n for n in names if n != chosen]
    candidates = [n for n in candidates if 'FAILED HEALTH CHECK' not in n] + [n for n in candidates if 'FAILED HEALTH CHECK' in n]
    log(f'PASS: device {chosen!r} selected (candidate fallback order: {candidates})')
    return chosen, candidates


def drive_wizard(h, client_id: str, device_name: str | None = None) -> list[str]:
    """Fill in and save the three-step Iso-VLM/LLM-Demo wizard.

    Sets the pipeline count, rechecks device health, sets the model and device, sets the base port and saves.

    Args:
        h (dict): Helpers from make_agent_helpers.
        client_id (str): GUI client session.
        device_name (str | None, optional): Device to prefer. Defaults to VLM_TEST_DEVICE_NAME when unset.

    Returns:
        list[str]: Device candidates in fallback order.
    """
    h['set_field'](client_id, 'How many parallel pipelines do you want to deploy?', PIPELINE_COUNT)
    log(f'PASS: pipeline count set to {PIPELINE_COUNT}')
    h['click'](client_id, 'Re-check device health')
    deadline = time.time() + 180.0
    while time.time() < deadline:
        if h['get_text'](client_id, 'device(s) healthy'):
            break
        time.sleep(2.0)
    else:
        die('device health check never reported a result in the Iso-VLM/LLM-Demo wizard')
    log('PASS: device health check completed')
    h['click'](client_id, 'Next')
    time.sleep(0.3)

    h['set_field'](client_id, 'Model', MODEL_NAME)
    log(f'PASS: model set to {MODEL_NAME!r}')

    _, candidates = discover_device_candidates(h, client_id, device_name or DEVICE_NAME_OVERRIDE)

    h['click'](client_id, 'Next')
    time.sleep(0.3)

    h['set_field'](client_id, 'Base port', BASE_PORT)
    log(f'PASS: base port set to {BASE_PORT}')
    h['click'](client_id, 'Save')
    if not h['wait_dialog'](client_id, False, timeout_s=10.0):
        die('Iso-VLM/LLM-Demo dialog never closed after Save')
    time.sleep(0.5)
    log('PASS: wizard saved -- canvas populated')
    return candidates


def compile_and_launch_vlm(h, client_id: str, timeout_s: float = VLLM_LAUNCH_TIMEOUT_S) -> str | None:
    """Click Compile and Launch Pipeline and wait for the launch notification.

    Args:
        h (dict): Helpers from make_agent_helpers.
        client_id (str): GUI client session.
        timeout_s (float, optional): Seconds to wait for a result. Defaults to VLLM_LAUNCH_TIMEOUT_S.

    Returns:
        str | None: None on success, 'device_fault' if the launch failed with a health-check failure,
        otherwise a description of the failure.
    """
    log('clicking Compile and Launch Pipeline')
    since_id = h['max_notif_id'](client_id)
    clicked = False
    for _ in range(30):
        if h['click'](client_id, 'Compile and Launch Pipeline', required=False).get('ok'):
            clicked = True
            break
        time.sleep(0.2)
    if not clicked:
        return 'Compile and Launch Pipeline button never became clickable'
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if h['notifications_match'](client_id, since_id, LAUNCH_SUCCESS_RE):
            texts = [n['message'] for n in h['notifications_since'](client_id, since_id)]
            launched = next((t for t in texts if LAUNCH_SUCCESS_RE.search(t)), None)
            log(f'PASS: {launched}')
            return None
        if h['notifications_match'](client_id, since_id, LAUNCH_FAILED_RE):
            texts = [n['message'] for n in h['notifications_since'](client_id, since_id)]
            failed = next((t for t in texts if LAUNCH_FAILED_RE.search(t)), None) or ''
            if is_device_fault(failed):
                log(f'device fault detected during compile/launch: {failed}')
                return 'device_fault'
            return failed
        time.sleep(2.0)
    return (f'Compile and Launch Pipeline produced neither a launch-success nor launch-failed '
            f'notification within {timeout_s}s')


def ensure_chat_endpoint_selected(h, client_id: str, timeout_s: float = 30.0) -> None:
    """Open the Benchmarking tab and wait until the (V/L)LM server chat dropdown shows the launched node, refreshing it meanwhile; calls die() on timeout."""
    log('clicking Benchmarking tab')
    h['click'](client_id, 'Benchmarking')
    time.sleep(0.5)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        value = h['get_field_value'](client_id, '(V/L)LM server') or ''
        if NODE_ID in value:
            log(f'PASS: (V/L)LM server dropdown shows {value!r}')
            return
        h['click'](client_id, 'chat refresh', required=False)
        time.sleep(1.5)
    die(f'{NODE_ID!r} never appeared in the (V/L)LM server chat dropdown within {timeout_s}s')


def read_avg_metrics(h, client_id: str) -> tuple[int, float, float | None]:
    """Parse the chat "avg (last N)" metrics label.

    Returns:
        tuple[int, float, float | None]: Sample count, average time to first token in seconds and average
        tokens per second (None when shown as n/a). (0, 0.0, None) if the label is absent.

    Raises:
        RuntimeError: If the label text cannot be parsed.
    """
    text = h['get_text'](client_id, 'avg (last')
    if not text:
        return 0, 0.0, None
    m = _AVG_METRICS_RE.search(text)
    if not m:
        raise RuntimeError(f'could not parse chat metrics label: {text!r}')
    n = int(m.group(1))
    avg_ttft = float(m.group(2))
    avg_tps = float(m.group(3)) if m.group(3) else None
    return n, avg_ttft, avg_tps


def send_chat_message(h, client_id: str, prompt: str, *, label: str, expected_count: int,
                       prior_ttft_sum: float, prior_tps_sum: float,
                       timeout_s: float = CHAT_REPLY_TIMEOUT_S) -> tuple[float, float | None, float, float]:
    """Send one chat message and wait for the metrics label to include its sample.

    The per-message values are derived from the change in the running sums (average times count).

    Args:
        h (dict): Helpers from make_agent_helpers.
        client_id (str): GUI client session.
        prompt (str): Message text.
        label (str): Name used in log lines.
        expected_count (int): Sample count the label must reach.
        prior_ttft_sum (float): Sum of TTFT values before this message.
        prior_tps_sum (float): Sum of tokens-per-second values before this message.
        timeout_s (float, optional): Seconds to wait. Defaults to CHAT_REPLY_TIMEOUT_S.

    Returns:
        tuple[float, float | None, float, float]: This message's TTFT, its tokens per second (None if unavailable),
        and the updated TTFT and tokens-per-second sums.
    """
    log(f'[{label}] filling Message with {prompt!r} and clicking Send')
    h['set_field'](client_id, 'Message', prompt)
    h['click'](client_id, 'Send')

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        n, avg_ttft, avg_tps = read_avg_metrics(h, client_id)
        if n == expected_count:
            ttft_sum = avg_ttft * n
            this_ttft = ttft_sum - prior_ttft_sum
            this_tps: float | None = None
            tps_sum = prior_tps_sum
            if avg_tps is not None:
                tps_sum = avg_tps * n
                this_tps = tps_sum - prior_tps_sum
            suffix = f', {this_tps:.1f} tok/s' if this_tps is not None else ' (tok/s unavailable)'
            log(f'PASS: [{label}] reply received -- TTFT {this_ttft:.2f}s{suffix}')
            return this_ttft, this_tps, ttft_sum, tps_sum
        time.sleep(1.0)
    die(f'[{label}] chat metrics label never reached sample count {expected_count} within {timeout_s}s')
    raise AssertionError('unreachable')


def clear_chat(h, client_id: str) -> None:
    """Click Clear to reset the chat session and its metrics buffer."""
    log('clicking Clear to reset chat session before sending anything')
    h['click'](client_id, 'Clear')
    time.sleep(0.3)
    log('PASS: chat cleared')


def run_chat_tests(h, client_id: str) -> dict[str, tuple[float, float | None]]:
    """Select the chat endpoint, clear the chat and send the joke and follow-up prompts.

    Returns:
        dict[str, tuple[float, float | None]]: TTFT and tokens per second keyed by 'joke' and 'followup'.
    """
    ensure_chat_endpoint_selected(h, client_id)
    clear_chat(h, client_id)
    results: dict[str, tuple[float, float | None]] = {}

    n0, avg_ttft0, avg_tps0 = read_avg_metrics(h, client_id)
    if n0 != 0:
        die(f'chat metrics buffer still has {n0} sample(s) after Clear -- Clear did not reset the session')
    ttft_sum0 = avg_ttft0 * n0
    tps_sum0 = (avg_tps0 or 0.0) * n0

    ttft1, tps1, ttft_sum1, tps_sum1 = send_chat_message(
        h, client_id, JOKE_PROMPT, label='joke', expected_count=n0 + 1,
        prior_ttft_sum=ttft_sum0, prior_tps_sum=tps_sum0)
    results['joke'] = (ttft1, tps1)

    ttft2, tps2, _, _ = send_chat_message(
        h, client_id, FOLLOWUP_PROMPT, label='followup', expected_count=n0 + 2,
        prior_ttft_sum=ttft_sum1, prior_tps_sum=tps_sum1)
    results['followup'] = (ttft2, tps2)
    return results


def run(h, client_id: str) -> dict[str, tuple[float, float | None]]:
    """Run the whole workflow: force stop, wizard, launch (retrying on device faults) and chat tests.

    When a launch fails with a device fault, the next candidate device is tried after another force stop and wizard pass.

    Returns:
        dict[str, tuple[float, float | None]]: Chat results from run_chat_tests.
    """
    force_stop_all(h, client_id)
    open_iso_vlm_demo_wizard(h, client_id)
    candidates = drive_wizard(h, client_id)

    tried: list[str] = []
    outcome: str | None = 'device_fault'
    for i, device_name in enumerate(candidates):
        tried.append(device_name)
        if i > 0:
            log(f'device {candidates[i - 1]!r} failed its health check at launch time -- '
                f'retrying with next candidate {device_name!r} '
                f'({len(candidates) - len(tried)} candidate(s) left after this)')
            force_stop_all(h, client_id)
            open_iso_vlm_demo_wizard(h, client_id)
            drive_wizard(h, client_id, device_name=device_name)
        outcome = compile_and_launch_vlm(h, client_id)
        if outcome != 'device_fault':
            break
    if outcome == 'device_fault':
        die(f'every candidate device faulted at launch time: {tried}')
    elif outcome is not None:
        die(outcome)

    results = run_chat_tests(h, client_id)
    log('ALL DONE -- fastapi-driven Iso-VLM/LLM-Demo release workflow finished')
    return results


def main() -> int:
    """Parse arguments, prepare the host, run the workflow and print the summary.

    Attaches to an existing session with --client-id, otherwise opens a headless Chromium tab and records
    console and page errors. Returns 0 without running when the vLLM artifact is not deployed.

    Returns:
        int: 0 on pass or skip, 1 on failure or any browser error.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8090')
    parser.add_argument('--client-id', default=None)
    args = parser.parse_args()
    prepare_host()
    if not require_vllm_artifacts('test_release_fastapi_llm', [MODEL_NAME]):
        return 0

    h = make_agent_helpers(args.base_url)
    results: dict[str, tuple[float, float | None]] = {}
    failed = False

    if args.client_id:
        log(f'attaching to existing live client_id={args.client_id} -- no new browser tab, '
            'no console/page-error capture')
        results = run(h, args.client_id)
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
                results = run(h, client_id)
            except SystemExit:
                failed = True
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
    for label in ('joke', 'followup'):
        if label in results:
            ttft, tps = results[label]
            tps_text = f'{tps:.1f} tok/s' if tps is not None else 'tok/s unavailable'
            print(f'{label}: TTFT {ttft:.2f}s, {tps_text}')
    ok = not (failed or console_errors or page_errors)
    print('test_release_fastapi_llm: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
