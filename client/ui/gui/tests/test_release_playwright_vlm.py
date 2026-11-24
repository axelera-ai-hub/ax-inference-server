#!/usr/bin/env python3
"""Release test that drives the Iso-VLM/LLM-Demo wizard of a running GUI with Playwright and chats, with attached images, with a smolvlm2-256m-video-instruct vLLM server."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from utils.host_server_prep import prepare_host, require_vllm_artifacts
from playwright.sync_api import Page, sync_playwright

MODEL_NAME = 'smolvlm2-256m-video-instruct'
DEVICE_NAME_OVERRIDE = os.environ.get('VLM_TEST_DEVICE_NAME')
PIPELINE_COUNT = '1'
TEMPERATURE = '0'
RESIZE_WIDTH = '256'
RESIZE_HEIGHT = '256'
BASE_PORT = '8001'
NODE_ID = 'vllm-1'
CHAT_IMAGE_FILENAMES = ('dancing_frame_t5_480p.jpg', 'dancing_frame_t15_480p.jpg')
JOKE_PROMPT = 'Tell me a joke.'
DESCRIBE_PROMPT = 'Describe the images.'
VLLM_LAUNCH_TIMEOUT_S = 300.0
CHAT_REPLY_TIMEOUT_S = 180.0
DEVICE_FAULT_SIGNATURES = ('failed a health check',)

_METRICS_RE = re.compile(r'TTFT\s+([\d.]+)s(?:\s*\xb7\s*([\d.]+)\s*tok/s)?')


def is_device_fault(text: str) -> bool:
    """Return True if the text contains a known device-fault signature."""
    return any(sig in text for sig in DEVICE_FAULT_SIGNATURES)


def log(msg: str) -> None:
    """Print a message prefixed with the current time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def _fill_field(scope, field_label: str, value: str) -> None:
    """Fill the text input of the Quasar field whose text contains field_label and press Tab to commit it."""
    field = scope.locator('.q-field').filter(has_text=field_label).first
    inp = field.locator('input').first
    inp.fill(value)
    inp.press('Tab')


def force_stop_all(page: Page) -> None:
    """Open the Pipeline Editor tab, click Force Stop All, confirm the dialog and wait for the result notification.

    A missing confirmation dialog or result notification is logged as a warning, not raised.
    """
    page.get_by_text('Pipeline Editor', exact=True).click()
    page.wait_for_timeout(500)
    log('clicking Force Stop All')
    page.get_by_role('button', name='Force Stop All', exact=True).click()
    dialog = page.locator('.q-dialog').last
    try:
        dialog.wait_for(state='visible', timeout=5000)
    except Exception:
        log('WARNING: Force Stop All confirmation dialog never appeared -- skipping')
        return
    dialog.get_by_role('button', name='Force stop all', exact=True).click()
    dialog.wait_for(state='hidden', timeout=10000)
    deadline = time.time() + 10.0
    result_text = None
    while time.time() < deadline:
        for t in page.locator('.q-notification__message').all_inner_texts():
            if t.startswith('Force-stopped') or t.startswith('No axinferencenet_grpc processes'):
                result_text = t
                break
        if result_text:
            break
        page.wait_for_timeout(500)
    if result_text:
        log(f'PASS: force stop all -> {result_text}')
    else:
        log('WARNING: force stop all did not produce the expected notification in time')
    page.wait_for_timeout(1000)


def open_iso_vlm_demo_wizard(page: Page):
    """Expand the Examples palette category if needed and open the Iso-VLM/LLM-Demo dialog.

    Returns:
        Locator: The opened dialog.
    """
    page.wait_for_selector('.vue-flow__pane', state='visible', timeout=10000)
    tree = page.locator('.q-tree')
    examples_label = tree.get_by_text('Examples', exact=True)
    iso_vlm_item = tree.get_by_text('Iso-VLM/LLM-Demo', exact=True)
    if not iso_vlm_item.is_visible():
        examples_label.locator(
            'xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " q-tree__node-header ")][1]'
            '//i[contains(@class,"q-tree__arrow")]'
        ).click()
        page.wait_for_timeout(500)
    log('clicking "Iso-VLM/LLM-Demo"')
    iso_vlm_item.click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=20000)
    log('PASS: Iso-VLM/LLM-Demo dialog opened')
    return dialog


def select_device(page: Page, dialog, preferred: str | None) -> tuple[str, list[str]]:
    """Open the wizard Device dropdown and pick a device.

    The preferred device is chosen if listed, otherwise the first one not marked FAILED HEALTH CHECK.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The wizard dialog.
        preferred (str | None): Device name to prefer.

    Returns:
        tuple[str, list[str]]: The chosen device and all candidates, chosen first, with unhealthy ones last.

    Raises:
        RuntimeError: If the dropdown lists no options.
    """
    device_field = dialog.locator('.q-field').filter(has_text='Device').first
    device_field.click()
    menu = page.locator('.q-menu')
    menu.wait_for(state='visible', timeout=10000)
    page.wait_for_timeout(150)
    names = [t.strip() for t in menu.locator('.q-item').all_inner_texts() if t.strip()]
    if not names:
        raise RuntimeError('Device dropdown rendered no options')
    chosen = preferred if preferred in names else next(
        (n for n in names if 'FAILED HEALTH CHECK' not in n), names[0])
    option = menu.locator('.q-item').filter(has_text=chosen).first
    option.wait_for(state='visible', timeout=10000)
    option.click()
    page.wait_for_timeout(200)
    candidates = [chosen] + [n for n in names if n != chosen]
    candidates = [n for n in candidates if 'FAILED HEALTH CHECK' not in n] + [n for n in candidates if 'FAILED HEALTH CHECK' in n]
    log(f'PASS: device {chosen!r} selected (candidate fallback order: {candidates})')
    return chosen, candidates


def drive_wizard(page: Page, dialog, device_name: str | None = None) -> list[str]:
    """Fill in and save the Iso-VLM/LLM-Demo wizard for the VLM model and check the resulting canvas.

    Sets the pipeline count, rechecks device health, selects the model and device, turns on enable_thinking and
    "Is VLM (image input)", sets temperature and image resize, sets the base port and saves.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The wizard dialog.
        device_name (str | None, optional): Device to prefer. Defaults to VLM_TEST_DEVICE_NAME when unset.

    Returns:
        list[str]: Device candidates in fallback order.

    Raises:
        RuntimeError: If a switch cannot be enabled or the canvas after Save does not have 3 nodes and 2 edges.
    """
    log(f'setting pipeline count to {PIPELINE_COUNT}')
    _fill_field(dialog, 'How many parallel pipelines do you want to deploy?', PIPELINE_COUNT)
    dialog.get_by_role('button', name='Re-check device health').click()
    dialog.get_by_text('device(s) healthy').wait_for(state='visible', timeout=180000)
    log('PASS: device health check completed')
    dialog.get_by_role('button', name='Next', exact=True).click()
    page.wait_for_timeout(300)

    log(f'selecting model {MODEL_NAME!r}')
    model_field = dialog.locator('.q-field').filter(has_text='Model').first
    model_field.click()
    option = page.locator('.q-menu .q-item').filter(has_text=MODEL_NAME).first
    option.wait_for(state='visible', timeout=10000)
    option.click()
    page.wait_for_timeout(200)

    _, candidates = select_device(page, dialog, device_name or DEVICE_NAME_OVERRIDE)

    log('enabling enable_thinking')
    thinking_switch = dialog.get_by_text('enable_thinking', exact=True).locator(
        'xpath=ancestor::div[@role="switch"][1]').first
    if thinking_switch.get_attribute('aria-checked') != 'true':
        thinking_switch.click()
        page.wait_for_timeout(200)
    if thinking_switch.get_attribute('aria-checked') != 'true':
        raise RuntimeError('failed to enable enable_thinking')
    log('PASS: enable_thinking enabled')

    log(f'confirming temperature is {TEMPERATURE}')
    _fill_field(dialog, 'temperature', TEMPERATURE)

    log('enabling "Is VLM (image input)"')
    is_vlm_switch = dialog.get_by_text('Is VLM (image input)', exact=True).locator(
        'xpath=ancestor::div[@role="switch"][1]').first
    if is_vlm_switch.get_attribute('aria-checked') != 'true':
        is_vlm_switch.click()
        page.wait_for_timeout(300)
    if is_vlm_switch.get_attribute('aria-checked') != 'true':
        raise RuntimeError('failed to enable Is VLM (image input)')
    log('PASS: Is VLM (image input) enabled')

    log(f'setting image resize to {RESIZE_WIDTH}x{RESIZE_HEIGHT}')
    _fill_field(dialog, 'Image resize width (px)', RESIZE_WIDTH)
    _fill_field(dialog, 'Image resize height (px)', RESIZE_HEIGHT)

    dialog.get_by_role('button', name='Next', exact=True).click()
    page.wait_for_timeout(300)

    log(f'setting base port to {BASE_PORT}')
    _fill_field(dialog, 'Base port', BASE_PORT)
    dialog.get_by_role('button', name='Save', exact=True).click()
    dialog.wait_for(state='hidden', timeout=10000)
    page.wait_for_timeout(500)

    n_nodes = page.locator('.vue-flow__node').count()
    n_edges = page.locator('.vue-flow__edge').count()
    if n_nodes != 3 or n_edges != 2:
        raise RuntimeError(f'canvas after Save has {n_nodes} node(s)/{n_edges} edge(s), expected 3/2')
    log(f'PASS: canvas has {n_nodes} nodes / {n_edges} edges (1 Input->(V/L)LM->Sink chain)')
    return candidates


def compile_and_launch_vlm(page: Page, timeout_s: float = VLLM_LAUNCH_TIMEOUT_S) -> tuple[str | None, str | None]:
    """Click Compile and Launch Pipeline and watch notifications until a launch result appears.

    Args:
        page (Page): Playwright page.
        timeout_s (float, optional): Seconds to wait. Defaults to VLLM_LAUNCH_TIMEOUT_S.

    Returns:
        tuple[str | None, str | None]: The "Launched ... vLLM VLM server" notification text and the
        "vLLM launch failed" text; both None on timeout.
    """

    seen: list[str] = list(page.locator('.q-notification__message').all_inner_texts())
    btn = page.get_by_role('button', name='Compile and Launch Pipeline', exact=True)
    log('clicking Compile and Launch Pipeline')
    btn.click()
    deadline = time.time() + timeout_s
    launched_text = failed_text = None
    while time.time() < deadline:
        for n in page.locator('.q-notification__message').all_inner_texts():
            if n not in seen:
                seen.append(n)
                log(f'notification: {n}')
                if n.startswith('Launched') and 'vLLM VLM server' in n:
                    launched_text = n
                if n.startswith('vLLM launch failed'):
                    failed_text = n
        if launched_text or failed_text:
            break
        page.wait_for_timeout(2000)
    return launched_text, failed_text


def ensure_chat_endpoint_selected(page: Page, node_id: str = NODE_ID, timeout_s: float = 30.0) -> None:
    """Open the Benchmarking tab and wait until the (V/L)LM server chat dropdown shows the node, refreshing it meanwhile.

    Raises:
        RuntimeError: If the node does not appear within the timeout.
    """
    log('switching to Benchmarking tab')
    page.get_by_text('Benchmarking', exact=True).click()
    page.wait_for_timeout(500)
    field = page.locator('.q-field').filter(has_text='(V/L)LM server')
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if node_id in field.first.inner_text():
            log(f'PASS: chat endpoint dropdown shows {node_id!r}')
            return
        page.locator('button[aria-label="chat refresh"]').click()
        page.wait_for_timeout(1500)
    raise RuntimeError(f'{node_id!r} never appeared in the (V/L)LM server chat dropdown within {timeout_s}s')


def _chat_log_locator(page: Page):
    """Return the locator of the chat log container (the element with a 220 px height style)."""
    return page.locator('[style*="height: 220px"]')


def clear_chat(page: Page) -> None:
    """Click Clear to reset the chat session and its metrics."""
    log('clicking Clear to reset chat session before sending anything')
    page.get_by_role('button', name='Clear', exact=True).click()
    page.wait_for_timeout(300)
    log('PASS: chat cleared')


def add_chat_image(page: Page, filename: str) -> None:
    """Attach one image to the chat through the Add image(s) dialog.

    Args:
        page (Page): Playwright page.
        filename (str): Name of the file to pick from the File / folder dropdown.
    """
    log(f'clicking Add image(s) -> {filename}')
    page.get_by_role('button', name='Add image(s)', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=5000)
    dialog.locator('.q-field').filter(has_text='File / folder').click()
    option = page.locator('.q-menu .q-item').filter(has_text=filename).first
    option.wait_for(state='visible', timeout=5000)
    option.click()
    dialog.get_by_role('button', name='Add', exact=True).click()
    dialog.wait_for(state='hidden', timeout=5000)
    log(f'PASS: attached image {filename!r}')


def send_chat_message(page: Page, prompt: str, *, label: str,
                       timeout_s: float = CHAT_REPLY_TIMEOUT_S) -> tuple[float, float | None]:
    """Send one chat message and wait for the reply card showing TTFT metrics.

    Args:
        page (Page): Playwright page.
        prompt (str): Message text.
        label (str): Name used in log lines and errors.
        timeout_s (float, optional): Seconds to wait. Defaults to CHAT_REPLY_TIMEOUT_S.

    Returns:
        tuple[float, float | None]: Time to first token in seconds and tokens per second (None if not shown).

    Raises:
        RuntimeError: If the reply reports an error, is empty, or has no TTFT within the timeout.
    """
    chat_log = _chat_log_locator(page)
    before_count = chat_log.locator('.q-card').count()
    log(f'[{label}] filling Message with {prompt!r} and clicking Send')
    page.locator('textarea').filter(has=page.locator('xpath=ancestor::*')).first
    message_field = page.locator('.q-field').filter(has_text='Message').last
    message_field.locator('textarea').first.fill(prompt)
    page.get_by_role('button', name='Send', exact=True).click()

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        count = chat_log.locator('.q-card').count()
        if count > before_count:
            text = chat_log.locator('.q-card').last.inner_text()
            if 'error:' in text.lower():
                raise RuntimeError(f'[{label}] chat reply errored: {text}')
            if '(empty response)' in text.lower():
                raise RuntimeError(f'[{label}] chat reply was empty: {text}')
            m = _METRICS_RE.search(text)
            if m:
                ttft = float(m.group(1))
                tok_per_sec = float(m.group(2)) if m.group(2) else None
                suffix = f', {tok_per_sec:.1f} tok/s' if tok_per_sec is not None else ' (tok/s unavailable)'
                log(f'PASS: [{label}] reply received -- TTFT {ttft:.2f}s{suffix}')
                return ttft, tok_per_sec
        page.wait_for_timeout(1000)
    raise RuntimeError(f'[{label}] chat reply never completed (no TTFT) within {timeout_s}s')


def run_chat_tests(page: Page) -> dict[str, tuple[float, float | None]]:
    """Select the chat endpoint, clear the chat, send a text prompt, attach the images and send an image prompt.

    Returns:
        dict[str, tuple[float, float | None]]: TTFT and tokens per second keyed by 'joke' and 'describe'.

    Raises:
        RuntimeError: If the attached-images label is not shown.
    """
    ensure_chat_endpoint_selected(page)
    clear_chat(page)
    results: dict[str, tuple[float, float | None]] = {}

    results['joke'] = send_chat_message(page, JOKE_PROMPT, label='joke')

    for filename in CHAT_IMAGE_FILENAMES:
        add_chat_image(page, filename)
    images_label = page.get_by_text(f'{len(CHAT_IMAGE_FILENAMES)}/', exact=False)
    if images_label.count() == 0:
        raise RuntimeError(f'expected {len(CHAT_IMAGE_FILENAMES)} attached image(s) label not found')
    log(f'PASS: {len(CHAT_IMAGE_FILENAMES)} image(s) attached')

    results['describe'] = send_chat_message(page, DESCRIBE_PROMPT, label='describe')
    return results


def main() -> int:
    """Parse arguments, prepare the host, drive the GUI in a visible Chromium window and print a summary.

    Retries the launch on the next device when it fails with a device fault. Chat tests run only after a successful launch.
    Saves a final screenshot under tests/. Returns 0 without running when the vLLM artifact is not deployed.

    Returns:
        int: 0 on pass or skip, 1 if any failure was recorded.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8090')
    args = parser.parse_args()
    prepare_host()
    if not require_vllm_artifacts('test_release_playwright_vlm', [MODEL_NAME]):
        return 0

    failures: list[str] = []
    chat_results: dict[str, tuple[float, float | None]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})

        console_messages = []
        page.on('console', lambda msg: console_messages.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda exc: console_messages.append(f'[pageerror] {exc}'))

        log(f'--- loading {args.base_url} ---')
        page.goto(args.base_url, wait_until='networkidle')

        try:
            force_stop_all(page)
            dialog = open_iso_vlm_demo_wizard(page)
            candidates = drive_wizard(page, dialog)
            tried: list[str] = []
            launched_text = failed_text = None
            for i, device_name in enumerate(candidates):
                tried.append(device_name)
                if i > 0:
                    log(f'device {candidates[i - 1]!r} failed its health check at launch time -- '
                        f'retrying with next candidate {device_name!r} '
                        f'({len(candidates) - len(tried)} candidate(s) left after this)')
                    force_stop_all(page)
                    dialog = open_iso_vlm_demo_wizard(page)
                    drive_wizard(page, dialog, device_name=device_name)
                launched_text, failed_text = compile_and_launch_vlm(page)
                if launched_text or not (failed_text and is_device_fault(failed_text)):
                    break
            if failed_text:
                log(f'FAIL: {failed_text}')
                failures.append(failed_text)
            if launched_text:
                log(f'PASS: {launched_text}')
            if not launched_text and not failed_text:
                failures.append('Compile and Launch Pipeline produced neither a launch-success nor '
                                 'launch-failed notification')
            if launched_text:
                chat_results = run_chat_tests(page)
        except Exception as exc:
            log(f'FAIL: {exc}')
            failures.append(str(exc))

        print('--- recent console/page messages ---')
        for line in console_messages[-30:]:
            print(line)

        page.screenshot(path='tests/_release_playwright_vlm_final.png', full_page=True)
        browser.close()

    print('\n=== SUMMARY ===')
    for label in ('joke', 'describe'):
        if label in chat_results:
            ttft, tok_per_sec = chat_results[label]
            tps_text = f'{tok_per_sec:.1f} tok/s' if tok_per_sec is not None else 'tok/s unavailable'
            print(f'{label}: TTFT {ttft:.2f}s, {tps_text}')
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        print('test_release_playwright_vlm: FAIL')
        return 1
    print('ALL STEPS PASSED')
    print('test_release_playwright_vlm: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
