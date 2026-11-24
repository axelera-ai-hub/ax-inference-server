#!/usr/bin/env python3
"""End-to-end release test that follows a user's workflow through the Three-Stage Conditional Cascade example with Playwright.

Configures the wizard, runs the health check, generates and launches the pipeline, then adds an image benchmark source
while optionally tracing AxMonitor utilisation (AXMONITOR_TRACE=1). Takes an optional base URL as the first
command-line argument (default http://127.0.0.1:8080).

Note:
    Failures are collected in a list and reported at the end rather than aborting the run.
"""

import re
import sys
import time

from playwright.sync_api import sync_playwright

from utils.axmonitor_trace import AxMonitorTracer
from utils.host_server_prep import prepare_host

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080'
PRIMARY_MODEL = 'yolox-m-coco-onnx'
SECONDARY_MODEL = 'yolo26npose-coco-onnx'
TERTIARY_MODEL = 'retinaface-mobilenet0.25-widerface-onnx'


def select_option(page, field_locator, option_text, timeout=10000):
    """Open a Quasar select and click the option whose text contains option_text.

    Args:
        page (Page): Playwright page.
        field_locator (Locator): The select field to open.
        option_text (str): Text of the option to pick.
        timeout (int, optional): Milliseconds to wait for the option. Defaults to 10000.
    """
    field_locator.click()
    item = page.locator('.q-menu .q-item').filter(has_text=option_text).first
    item.wait_for(state='visible', timeout=timeout)
    item.click()
    page.wait_for_timeout(300)


DEVICE_BUSY_SIGNATURES = ('allocate AI cores', 'axr_device_connect', 'Address already in use',
                           'a device health check is currently using')
DEVICE_FAULT_SIGNATURES = ('faulty device(s) detected', 'ZE_RESULT_ERROR_DEVICE_LOST')
STAGE_LABELS = ['Primary model', 'Secondary model', 'Conditional tertiary model']


def force_stop_all(page):
    """Open the Pipeline Editor tab and click Force Stop All, confirming the dialog if one appears; a missing dialog is ignored."""
    page.get_by_role('tab', name='Pipeline Editor').click()
    page.wait_for_timeout(500)
    page.get_by_text('Force Stop All', exact=True).click()
    confirm_dialog = page.locator('.q-dialog').last
    try:
        confirm_dialog.wait_for(state='visible', timeout=5000)
        confirm_dialog.get_by_text('Force Stop All', exact=True).click()
        confirm_dialog.wait_for(state='hidden', timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(2000)


def ensure_opencl_disabled(page, failures) -> None:
    """Switch the OpenCL global setting off if it is on.

    Args:
        page (Page): Playwright page.
        failures (list[str]): Receives a message if the switch is still on afterwards.
    """
    switch = page.get_by_text('OpenCL', exact=True).locator('xpath=ancestor::div[@role="switch"]').first
    if switch.get_attribute('aria-checked') != 'false':
        switch.click()
        page.wait_for_timeout(300)
    state = switch.get_attribute('aria-checked')
    if state != 'false':
        failures.append(f'failed to disable the OpenCL global setting (aria-checked={state!r})')
        print(f'FAIL: failed to disable the OpenCL global setting (aria-checked={state!r})')
        return
    print('PASS: OpenCL global setting disabled')


def _find_prebuilt_catalog_option(page, menu, model_name, max_scroll_steps=150):
    """Scroll a virtualised dropdown menu to its top, then downwards until the option for a model is visible.

    Args:
        page (Page): Playwright page.
        menu (Locator): The open dropdown menu.
        model_name (str): Text of the option to find.
        max_scroll_steps (int, optional): Limit for each scroll direction. Defaults to 150.

    Returns:
        Locator | None: The visible option, or None if it was not found.
    """
    prev_first_text = None
    for _ in range(max_scroll_steps):
        menu.hover()
        page.mouse.wheel(0, -600)
        page.wait_for_timeout(60)
        texts = menu.locator('.q-item').all_inner_texts()
        first_text = texts[0] if texts else None
        if first_text is not None and first_text == prev_first_text:
            break
        prev_first_text = first_text

    for _ in range(max_scroll_steps):
        option = menu.locator('.q-item').filter(has_text=model_name).first
        if option.count() > 0 and option.is_visible():
            return option
        menu.hover()
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(60)
    return None


def select_model_with_fallback(page, dialog, stage_label, model_name, download_timeout_s=300.0):
    """Select a model for one stage, from the $SDK_ROOT/build dropdown or else from the prebuilt catalog.

    For a prebuilt model, waits until the dropdown shows it as downloaded.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        stage_label (str): Stage name used in messages.
        model_name (str): Model to select.
        download_timeout_s (float, optional): Seconds to wait for a prebuilt download. Defaults to 300.0.

    Raises:
        RuntimeError: If the prebuilt checkbox or model is not found, or the download fails or times out.
    """

    build_field = dialog.locator('.q-field:visible').filter(has_text='Model (.axnet, from host server)')
    try:
        build_field.first.wait_for(state='visible', timeout=20000)
    except Exception:
        pass
    if build_field.count() > 0:
        current = build_field.inner_text()
        if model_name in current:
            print(f'PASS: {stage_label}: {model_name!r} already selected under $SDK_ROOT/build')
            return
        build_field.click()
        option = page.locator('.q-menu .q-item').filter(has_text=model_name).first
        try:
            option.wait_for(state='visible', timeout=3000)
            option.click()
            page.wait_for_timeout(300)
            print(f'PASS: {stage_label}: selected {model_name!r} from the $SDK_ROOT/build dropdown')
            return
        except Exception:
            page.keyboard.press('Escape')
            print(f'{stage_label}: {model_name!r} not available under $SDK_ROOT/build -- '
                  'falling back to prebuilt models')
    else:
        print(f'{stage_label}: no $SDK_ROOT/build dropdown present (no vision models built on this host) -- '
              'falling back to prebuilt models')

    checkbox_labels = dialog.get_by_text('Use prebuilt models', exact=False)
    checkbox = None
    for i in range(checkbox_labels.count()):
        cand = checkbox_labels.nth(i).locator('xpath=ancestor::div[@role="checkbox"][1]')
        if cand.is_visible():
            checkbox = cand
            break
    if checkbox is None:
        raise RuntimeError(f'{stage_label}: could not find a visible "Use prebuilt models" checkbox')
    if checkbox.get_attribute('aria-checked') != 'true':
        checkbox.click()

    prebuilt_select = dialog.locator('.q-field:visible').filter(has_text='Prebuilt model')
    prebuilt_select.first.wait_for(state='visible', timeout=60000)
    print(f'PASS: {stage_label}: prebuilt model catalog fetched')

    prebuilt_select.first.click()
    menu = page.locator('.q-menu').last
    menu.wait_for(state='visible', timeout=5000)
    prebuilt_option = _find_prebuilt_catalog_option(page, menu, model_name)
    if prebuilt_option is None:
        raise RuntimeError(f'{stage_label}: {model_name!r} not found in the prebuilt catalog dropdown '
                            'after scrolling through it')
    prebuilt_option.click()
    print(f'{stage_label}: selected {model_name!r} from the prebuilt catalog -- '
          'waiting for its artifacts to download')

    deadline = time.time() + download_timeout_s
    downloaded = False
    while time.time() < deadline:
        notif_texts = page.locator('.q-notification__message').all_inner_texts()
        for t in notif_texts:
            if model_name in t and ('failed' in t.lower() or 'could not reach' in t.lower()):
                raise RuntimeError(f'failed to download prebuilt model {model_name!r}: {t}')
        current_text = prebuilt_select.first.inner_text()
        if model_name in current_text and 'downloaded' in current_text.lower():
            downloaded = True
            break
        page.wait_for_timeout(1000)
    if not downloaded:
        raise RuntimeError(f'prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')
    print(f'PASS: {stage_label}: {model_name!r} downloaded')


def set_cores(dialog, device_index, cores, failures, stage_label):
    """Fill the "Cores on Device N" field of the current stage.

    Args:
        dialog (Locator): The cascade dialog.
        device_index (int): Device whose core field is set.
        cores (int): Number of cores.
        failures (list[str]): Receives a message if the field is missing.
        stage_label (str): Stage name used in messages.
    """
    field = dialog.locator('.q-field:visible').filter(has_text=f'Cores on Device {device_index}')
    if field.count() == 0:
        failures.append(f'{stage_label}: "Cores on Device {device_index}" field not found')
        print(f'FAIL: {stage_label} -- no cores field for Device {device_index}')
        return
    field.locator('input').fill(str(cores))
    print(f'PASS: {stage_label} cores on Device {device_index} set to {cores}')


def select_device(page, dialog, stage_label, device, cores, failures):
    """Make one stage use only the given device and set its core count.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        stage_label (str): Stage whose tab is opened.
        device (int): Device index to select; all other devices are deselected.
        cores (int): Cores on that device.
        failures (list[str]): Receives errors from set_cores.
    """

    dialog.get_by_text(stage_label, exact=True).click()
    page.wait_for_timeout(300)
    devices_field = dialog.locator('.q-field:visible').filter(has_text='Devices (select one or more)')
    devices_field.click()
    menu = page.locator('.q-menu').last
    menu.wait_for(state='visible', timeout=10000)
    page.wait_for_timeout(200)
    for _ in range(40):
        changed = False
        for item in menu.locator('[role="option"]').all():
            m = re.search(r'Device\s+(\d+)\b', item.inner_text())
            if not m:
                continue
            idx = int(m.group(1))
            selected = item.get_attribute('aria-selected') == 'true'
            wanted = idx == device
            if selected != wanted:
                item.click()
                page.wait_for_timeout(150)
                changed = True
                break
        if not changed:
            break
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    set_cores(dialog, device, cores, failures, stage_label)
    print(f'PASS: {stage_label} moved to device {device}, {cores} core(s)')


def healthy_device_candidates(health_text, stage_labels):
    """Find the devices that are healthy for every stage.

    Parses lines of the form "<stage>: n/m device(s) healthy (indices: a, b)".

    Args:
        health_text (str): Health check result text.
        stage_labels (list[str]): Stage names that must all be reported.

    Returns:
        list[int]: Device indices healthy for all stages, device 0 first then ascending; empty if any stage is missing.
    """
    per_stage = {}
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


def configure_wizard(page, failures):
    """Open the Three-Stage Conditional Cascade dialog and fill in all three stages and the condition.

    Sets models (failures are recorded, not raised), meta_key_override and cores per stage, the kpts_conf_gt condition
    on meta_key pose with indices 0,1,2 and value 0.5, and filter classes 0.

    Args:
        page (Page): Playwright page.
        failures (list[str]): Receives step failures.

    Returns:
        Locator: The cascade dialog.
    """
    examples_label = page.locator('.q-tree').get_by_text('Examples', exact=True)
    examples_label.locator(
        'xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " q-tree__node-header ")][1]'
        '//i[contains(@class,"q-tree__arrow")]'
    ).click()
    page.wait_for_timeout(500)
    page.locator('.q-tree').get_by_text('Three-Stage Conditional Cascade', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=10000)
    print('PASS: Three-Stage Conditional Cascade dialog opened')

    try:
        select_model_with_fallback(page, dialog, 'Primary model', PRIMARY_MODEL)
    except Exception as exc:
        failures.append(f'Primary model selection failed: {exc}')
        print(f'FAIL: Primary model selection failed: {exc}')
    primary_meta = dialog.locator('.q-field:visible').filter(has_text='meta_key_override').locator('input')
    primary_meta.fill('det')
    set_cores(dialog, 0, 1, failures, 'Primary')
    print(f'PASS: primary stage set to {PRIMARY_MODEL}, meta_key_override=det')

    dialog.get_by_text('Secondary model', exact=True).click()
    page.wait_for_timeout(300)
    try:
        select_model_with_fallback(page, dialog, 'Secondary model', SECONDARY_MODEL)
    except Exception as exc:
        failures.append(f'Secondary model selection failed: {exc}')
        print(f'FAIL: Secondary model selection failed: {exc}')
    secondary_meta = dialog.locator('.q-field:visible').filter(has_text='meta_key_override').locator('input')
    secondary_meta.fill('pose')
    set_cores(dialog, 0, 2, failures, 'Secondary')
    print(f'PASS: secondary stage set to {SECONDARY_MODEL}, meta_key_override=pose')

    dialog.get_by_text('Conditional tertiary model', exact=True).click()
    page.wait_for_timeout(300)
    try:
        select_model_with_fallback(page, dialog, 'Conditional tertiary model', TERTIARY_MODEL)
    except Exception as exc:
        failures.append(f'Tertiary model selection failed: {exc}')
        print(f'FAIL: Tertiary model selection failed: {exc}')
    tertiary_meta = dialog.locator('.q-field:visible').filter(has_text='meta_key_override').locator('input')
    tertiary_meta.fill('face')
    print(f'PASS: tertiary stage set to {TERTIARY_MODEL}, meta_key_override=face')
    set_cores(dialog, 0, 1, failures, 'Tertiary')

    type_select = dialog.locator('.q-field:visible').filter(has_text='type').first
    select_option(page, type_select, 'kpts_conf_gt')
    meta_key_label = dialog.locator(':visible').get_by_text('predicate meta_key', exact=True)
    predicate_meta_key = meta_key_label.locator(
        'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " q-field ")][1]//input'
    )
    predicate_meta_key.fill('pose')
    predicate_indices = dialog.locator('.q-field:visible').filter(
        has_text='indices (comma-separated, e.g. 0,1,2)').locator('input')
    predicate_indices.fill('0,1,2')
    predicate_value = dialog.locator('.q-field:visible').filter(has_text='value (confidence threshold)').locator('input')
    predicate_value.fill('0.5')
    print('PASS: condition set to kpts_conf_gt(meta_key=pose, indices=0,1,2, value=0.5)')

    filter_classes = dialog.locator('.q-field:visible').filter(has_text='classes (optional').locator('input')
    filter_classes.fill('0')
    print('PASS: Filter classes set to 0 (person)')
    return dialog


def run_health_check(page, dialog, failures, timeout_s=240.0):
    """Click Run Health Check (all models) and wait until all three stages report a result.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        failures (list[str]): Receives a message if a stage is unhealthy or the check failed.
        timeout_s (float, optional): Seconds to wait. Defaults to 240.0.

    Returns:
        str | None: The result text, or None if a device-busy notification was seen.
    """

    seen_notifications = []
    health_btn = dialog.get_by_text('Run Health Check (all models)', exact=True)
    health_btn.click()
    print('health check started, polling...')
    health_label = dialog.locator('.text-caption.text-grey-7').first
    deadline = time.time() + timeout_s
    last_text = ''
    while time.time() < deadline:
        notifs = page.locator('.q-notification__message').all_inner_texts()
        for n in notifs:
            if n not in seen_notifications:
                seen_notifications.append(n)
                print(f'notification: {n}')
        if any(sig in ' '.join(seen_notifications) for sig in DEVICE_BUSY_SIGNATURES):
            print('device busy (health check lock not yet released)')
            return None
        last_text = health_label.inner_text()
        lines = [l for l in last_text.split('\n') if l.strip()]
        if 'Checking' not in last_text and len(lines) >= 3:
            break
        page.wait_for_timeout(2000)
    print(f'health check result:\n{last_text}')
    if re.search(r'(?<!\d)0/\d+ device\(s\) healthy', last_text) or 'health check failed' in last_text:
        failures.append(f'Health check reported unhealthy/failed stage(s): {last_text}')
        print('FAIL: health check did not report healthy devices for all three stages')
    else:
        print('PASS: health check completed')
    return last_text


def generate_pipeline_step(page, dialog, failures):
    """Click Generate Pipeline and record a failure if the dialog does not close within 10 s.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        failures (list[str]): Receives the failure message.
    """
    dialog.get_by_text('Generate Pipeline', exact=True).click()
    page.wait_for_timeout(1500)
    try:
        dialog.wait_for(state='hidden', timeout=10000)
        print('PASS: Generate Pipeline closed the dialog (graph pushed to canvas)')
    except Exception:
        failures.append('Generate Pipeline dialog did not close -- likely a validation error on-canvas')
        print('FAIL: cascade dialog still open after Generate Pipeline click')
        print('visible text near dialog:', dialog.inner_text()[:500])
    node_texts = page.locator('.vue-flow__node').all_inner_texts()
    print('canvas nodes after Generate Pipeline:', node_texts)


def generate_config_yaml_step(page, failures):
    """Disable OpenCL, open Generate Config YAML, check the YAML mentions det, pose, face and kpts_conf_gt, and save it.

    Args:
        page (Page): Playwright page.
        failures (list[str]): Receives failures.
    """
    ensure_opencl_disabled(page, failures)
    page.get_by_text('Generate Config YAML', exact=True).click()
    yaml_dialog = page.locator('.q-dialog').last
    try:
        yaml_dialog.wait_for(state='visible', timeout=10000)
        yaml_text = yaml_dialog.locator('textarea').input_value()
        print('--- generated YAML (first 3000 chars) ---')
        print(yaml_text[:3000])
        missing = [k for k in ('det', 'pose', 'face', 'kpts_conf_gt') if k not in yaml_text]
        if missing:
            failures.append(f'Generated YAML missing expected strings: {missing}')
            print(f'FAIL: generated YAML missing {missing}')
        else:
            print('PASS: generated YAML contains det/pose/face/kpts_conf_gt strings')
        yaml_dialog.get_by_text('Save', exact=True).click()
        yaml_dialog.wait_for(state='hidden', timeout=10000)
        print('PASS: Generate Config YAML -> Save completed')
    except Exception as exc:
        failures.append(f'Generate Config YAML step failed: {exc}')
        print(f'FAIL: Generate Config YAML step failed: {exc}')


def compile_and_launch_step(page, failures, timeout_s=240.0):
    """Click Compile and Launch Pipeline and watch notifications, handling busy devices and OpenCL errors.

    Retries up to three times. A device-busy notification triggers Force Stop All and a retry; an OpenCL platform error
    disables OpenCL, regenerates the config YAML and retries once. A device fault is returned for the caller to handle.
    The result is tentative: success means no negative notification was seen.

    Args:
        page (Page): Playwright page.
        failures (list[str]): Receives failures.
        timeout_s (float, optional): Seconds to wait per attempt. Defaults to 240.0.

    Returns:
        str: 'ok', 'failed' or 'device_fault'.
    """

    opencl_error_signatures = ('OpenCL platform',)
    opencl_retried = False
    for attempt in range(3):
        compile_btn = page.get_by_text('Compile and Launch Pipeline', exact=True)
        compile_btn.click()
        print('compile/launch started, waiting for completion notification...')
        deadline = time.time() + timeout_s
        seen_notifications = []
        negative_seen = False
        device_busy = False
        device_fault = False
        opencl_error = False
        while time.time() < deadline:
            notifs = page.locator('.q-notification__message').all_inner_texts()
            for n in notifs:
                if n not in seen_notifications:
                    seen_notifications.append(n)
                    print(f'notification: {n}')
            classes = page.locator('.q-notification').evaluate_all('els => els.map(e => e.className)')
            if any('negative' in c for c in classes):
                negative_seen = True
            texts_joined = ' '.join(seen_notifications)
            if any(sig in texts_joined for sig in DEVICE_BUSY_SIGNATURES):
                device_busy = True
                break
            if any(sig in texts_joined for sig in DEVICE_FAULT_SIGNATURES):
                device_fault = True
                break
            if any(sig in texts_joined for sig in opencl_error_signatures):
                opencl_error = True
                break
            if any(('launch' in n.lower() or 'compiled' in n.lower() or 'running' in n.lower())
                   for n in seen_notifications):
                break
            page.wait_for_timeout(3000)
        if device_fault:
            print(f'device fault detected during compile/launch: {seen_notifications}')
            return 'device_fault'
        if device_busy and attempt < 2:
            print('device busy (health check lock not yet released) -- Force Stop All and retrying')
            force_stop_all(page)
            continue
        if opencl_error and not opencl_retried:
            print('OpenCL driver error -- disabling OpenCL and regenerating config YAML before retrying')
            generate_config_yaml_step(page, failures)
            opencl_retried = True
            continue
        if negative_seen:
            failures.append(f'Compile and Launch Pipeline raised a negative notification: {seen_notifications}')
            print('FAIL: negative notification seen during compile/launch')
            return 'failed'
        print('PASS (tentative): no negative notification seen during compile/launch')
        return 'ok'
    return 'failed'


def main() -> int:
    """Run the end-to-end cascade workflow and print a summary.

    Prepares the host with all three models, configures the wizard, retries the health check while devices are busy,
    launches on the first device that works (trying the next on device faults), adds a 50 FPS image source on the
    Benchmarking tab and reports the AxMonitor trace summary. Warnings from the trace do not fail the test; page errors do.
    Saves a final screenshot under tests/.

    Returns:
        int: 0 if all steps passed, 1 otherwise.
    """
    prepare_host([PRIMARY_MODEL, SECONDARY_MODEL, TERTIARY_MODEL])
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page_errors = []
        console_errors = []
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)

        print(f'--- loading {BASE_URL} ---')
        page.goto(BASE_URL, wait_until='networkidle')
        page.get_by_role('tab', name='Pipeline Editor').click()
        page.wait_for_selector('.vue-flow__node', state='visible', timeout=15000)
        print('page loaded, canvas visible')

        dialog = configure_wizard(page, failures)

        health_text = None
        for attempt in range(3):
            health_text = run_health_check(page, dialog, failures)
            if health_text is not None:
                break
            print(f'retrying health check after device-busy (attempt {attempt + 1}/3)')
            force_stop_all(page)
            dialog = configure_wizard(page, failures)
        if health_text is None:
            failures.append('health check never ran -- device busy on every retry attempt')
            print('FAIL: health check device busy on every retry attempt')
            health_text = ''
        candidates = healthy_device_candidates(health_text, STAGE_LABELS)
        if not candidates:
            failures.append(f'no single device is healthy for every stage of this cascade -- not a go:\n{health_text}')
            print(f'FAIL: no device is healthy for every stage:\n{health_text}')
            candidates = [0]
        else:
            print(f'PASS: candidate device(s) to try, in order: {candidates}')

        tried = []
        outcome = 'device_fault'
        for i, device in enumerate(candidates):
            tried.append(device)
            if i > 0:
                force_stop_all(page)
                dialog = configure_wizard(page, failures)
            if device != 0:
                select_device(page, dialog, 'Primary model', device, 1, failures)
                select_device(page, dialog, 'Secondary model', device, 2, failures)
                select_device(page, dialog, 'Conditional tertiary model', device, 1, failures)
            generate_pipeline_step(page, dialog, failures)
            generate_config_yaml_step(page, failures)
            outcome = compile_and_launch_step(page, failures)
            if outcome != 'device_fault':
                break
            print(f'device {device} faulted at compile time -- '
                  f'{len(candidates) - len(tried)} candidate(s) left to try')
        if outcome == 'device_fault':
            failures.append(f'every candidate device faulted at compile time: {tried}')
            print(f'FAIL: every candidate device faulted at compile time: {tried}')

        tracer = AxMonitorTracer(BASE_URL)
        if tracer.error:
            print(f'WARNING: {tracer.error}')

        page.get_by_role('tab', name='Benchmarking').click()
        page.wait_for_timeout(1000)
        page.get_by_text('Add file', exact=True).click()
        add_file_dialog = page.locator('.q-dialog').last
        add_file_dialog.wait_for(state='visible', timeout=10000)
        file_select = add_file_dialog.locator('.q-field').filter(has_text='File / folder')
        select_option(page, file_select, 'dancing_frame_t15_480p.jpg')
        fps_input = add_file_dialog.locator('.q-field').filter(has_text='FPS').locator('input')
        fps_input.fill('50')
        open_btn = add_file_dialog.get_by_text('Open', exact=True)
        open_btn.click()
        tracer.start()
        page.wait_for_timeout(3000)
        print('PASS: benchmark image source added at 50 FPS')

        page.wait_for_timeout(5000)
        if tracer.enabled:
            page.wait_for_timeout(10000)
        tracer.stop()

        trace_summary = tracer.summarize()
        if trace_summary is not None:
            print(f'--- AxMonitor trace summary --- {trace_summary}')
            if trace_summary['error_count'] == trace_summary['sample_count']:
                print(f'WARNING: AxMonitor trace -- all {trace_summary["sample_count"]} poll(s) of /api/v1/monitor/stats failed (not a test failure)')
            elif trace_summary['max_core_utilization_pct'] <= 0 and trace_summary['max_ddr_utilization_pct'] <= 0:
                print(f'WARNING: AxMonitor trace -- core/DDR utilization stayed at 0 across {trace_summary["sample_count"]} samples while frames were streaming (not a test failure)')
            else:
                print('PASS: AxMonitor trace observed non-zero utilization during active benchmark run')

        print('--- page errors ---')
        for e in page_errors:
            print(e)
            failures.append(f'page error: {e}')
        print('--- console errors ---')
        for e in console_errors:
            print(e)

        page.screenshot(path='tests/_cascade3_e2e_final.png', full_page=True)
        browser.close()

    print('\n=== SUMMARY ===')
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        return 1
    print('ALL STEPS PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
