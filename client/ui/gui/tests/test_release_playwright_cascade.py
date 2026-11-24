#!/usr/bin/env python3
"""Release test that builds the Two-Stage Cascade example in the GUI with Playwright, launches it and checks it sustains the target FPS.

Takes an optional base URL as the first command-line argument (default http://127.0.0.1:8090).
"""

import os
import re
import sys
from utils.host_server_prep import prepare_host
import time

from playwright.sync_api import sync_playwright

from test_release_playwright_isovision import (
    force_stop_all,
    ensure_opencl_disabled,
    generate_config_yaml,
    compile_and_launch_vision,
    _remove_all_benchmark_sources,
    read_raw_infer_fps,
    assert_fps_stable,
    assert_fps_mean_stable,
)

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090'
PRIMARY_MODEL = 'yolox-m-coco-onnx'
SECONDARY_MODEL = 'yolo26npose-coco-onnx'
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
BACKPRESSURE_CAP = 1000
FPS_STEPS = [5, 30]
FPS_GATE_SETTLE_S = 5.0
FPS_GATE_HOLD_S = 15.0
FPS_GATE_TOLERANCE_FRAC = 0.1

DEVICE_FAULT_SIGNATURES = ('faulty device(s) detected', 'ZE_RESULT_ERROR_DEVICE_LOST')
STAGE_LABELS = ['Primary model', 'Secondary model']

MONITOR_CHECKBOX_LABELS = [
    'CPU utilization',
    'Memory utilization',
    'Aggregate core utilization %',
    'Aggregate MVM utilization %',
    'Aggregate DDR utilization %',
]


def select_option(page, field_locator, option_text, timeout=30000):
    """Open a Quasar select and click the option whose text contains option_text.

    Args:
        page (Page): Playwright page.
        field_locator (Locator): The select field to open.
        option_text (str): Text of the option to pick.
        timeout (int, optional): Milliseconds to wait for the option. Defaults to 30000.
    """
    field_locator.click()
    item = page.locator('.q-menu .q-item').filter(has_text=option_text).first
    item.wait_for(state='visible', timeout=timeout)
    item.click()
    page.wait_for_timeout(300)


def open_two_stage_cascade_wizard(page):
    """Expand the Examples palette category and open the Two-Stage Cascade dialog.

    Returns:
        Locator: The opened dialog.
    """
    tree = page.locator('.q-tree')
    examples_label = tree.get_by_text('Examples', exact=True)
    examples_label.locator(
        'xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " q-tree__node-header ")][1]'
        '//i[contains(@class,"q-tree__arrow")]'
    ).click()
    page.wait_for_timeout(500)
    tree.get_by_text('Two-Stage Cascade', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=10000)
    print('PASS: Two-Stage Cascade dialog opened')
    return dialog


def configure_stage(page, dialog, stage_label, model_name, cores, meta_key):
    """Set the model, meta_key_override and core count of one stage in the cascade dialog.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        stage_label (str): Stage name; for other than 'Primary model' its tab is clicked first.
        model_name (str): Model to pick in the "Model (.axnet, from host server)" dropdown.
        cores (int): Value for the "Cores on Device 0" field.
        meta_key (str): Value for meta_key_override.
    """
    if stage_label != 'Primary model':
        dialog.get_by_text(stage_label, exact=True).click()
        page.wait_for_timeout(300)
    axnet_field = dialog.locator('.q-field:visible').filter(has_text='Model (.axnet, from host server)')
    select_option(page, axnet_field, model_name)
    meta_input = dialog.locator('.q-field:visible').filter(has_text='meta_key_override').locator('input')
    meta_input.fill(meta_key)
    cores_field = dialog.locator('.q-field:visible').filter(has_text='Cores on Device 0').locator('input')
    cores_field.fill(str(cores))
    cores_field.press('Tab')
    print(f'PASS: {stage_label} set to {model_name}, device 0, {cores} core(s), meta_key_override={meta_key}')


def run_health_check(dialog, timeout_s=180.0):
    """Click Run Health Check (all models) in the dialog and wait until every stage reports a result.

    Args:
        dialog (Locator): The cascade dialog.
        timeout_s (float, optional): Seconds to wait. Defaults to 180.0.

    Returns:
        str: The health result text.

    Raises:
        RuntimeError: If the result says the health check failed.
    """
    print('clicking Run Health Check (all models)')
    dialog.get_by_text('Run Health Check (all models)', exact=True).click()
    health_label = dialog.locator('.text-caption.text-grey-7').first
    deadline = time.time() + timeout_s
    last_text = ''
    while time.time() < deadline:
        last_text = health_label.inner_text()
        lines = [l for l in last_text.split('\n') if l.strip()]
        if lines and all('Checking' not in l for l in lines) and len(lines) >= 2:
            break
        time.sleep(2.0)
    print(f'health check result:\n{last_text}')
    if 'health check failed' in last_text.lower():
        raise RuntimeError(f'health check failed: {last_text}')
    print('PASS: health check -- both stages reported')
    return last_text


def healthy_device_candidates(health_text, stage_labels):
    """Find the devices that are healthy for every stage.

    Parses lines of the form "<stage>: n/m device(s) healthy (indices: a, b)".

    Args:
        health_text (str): Text from run_health_check.
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


def select_device(page, dialog, stage_label, device, cores):
    """Make one stage use only the given device and set its core count.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        stage_label (str): Stage whose tab is opened.
        device (int): Device index to select; all other devices are deselected.
        cores (int): Value for the "Cores on Device <device>" field.
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
    cores_field = dialog.locator('.q-field:visible').filter(has_text=f'Cores on Device {device}').locator('input')
    cores_field.fill(str(cores))
    cores_field.press('Tab')
    print(f'PASS: {stage_label} moved to device {device}, {cores} core(s)')


def generate_pipeline(page, dialog):
    """Click Generate Pipeline, wait for the dialog to close and print the resulting canvas node texts."""
    print('clicking Generate Pipeline')
    dialog.get_by_text('Generate Pipeline', exact=True).click()
    dialog.wait_for(state='hidden', timeout=10000)
    page.wait_for_timeout(500)
    node_texts = page.locator('.vue-flow__node').all_inner_texts()
    print(f'PASS: Generate Pipeline closed the dialog -- canvas nodes: {node_texts}')


def enable_monitor_checkboxes(page):
    """Tick the monitor checkboxes listed in MONITOR_CHECKBOX_LABELS.

    Controls that are missing, disabled or do not toggle are reported on stderr as warnings.

    Returns:
        tuple[list[str], list[str]]: Labels that were enabled, and descriptions of those that could not be.
    """
    enabled, unavailable = [], []
    for label in MONITOR_CHECKBOX_LABELS:
        cb_label = page.get_by_text(label, exact=True).first
        checkbox = cb_label.locator('xpath=ancestor::div[@role="checkbox"][1]')
        if checkbox.count() == 0:
            unavailable.append(f'{label} (control not found)')
            continue
        if checkbox.get_attribute('aria-disabled') == 'true':
            unavailable.append(f'{label} (disabled -- axmonitor/axsystemserver not reachable)')
            continue
        if checkbox.get_attribute('aria-checked') != 'true':
            checkbox.click()
            page.wait_for_timeout(200)
        if checkbox.get_attribute('aria-checked') == 'true':
            enabled.append(label)
        else:
            unavailable.append(f'{label} (click did not take)')
    for label in enabled:
        print(f'PASS: enabled monitor checkbox {label!r}')
    for label in unavailable:
        print(f'WARNING: could not enable monitor checkbox {label!r}', file=sys.stderr)
    return enabled, unavailable


def _read_aggregate_fps(page):
    """Read the latest value of the Plotly trace named "Aggregate FPS...".

    Returns:
        float | None: The last y value, or None if no such trace has data.
    """
    return page.evaluate("""
        () => {
            for (const gd of document.querySelectorAll('.js-plotly-plot')) {
                if (!gd.data) continue;
                const trace = gd.data.find(t => (t.name || '').startsWith('Aggregate FPS'));
                if (trace && trace.y && trace.y.length) return trace.y[trace.y.length - 1];
            }
            return null;
        }
    """)


def add_benchmark_source_and_ramp(page, filename, steps, settle_s, hold_s, tolerance_frac):
    """Add an image benchmark source and step its target FPS through the given values, gating each step.

    Every step checks that raw infer_fps holds near the target. The highest step uses the mean-based gate
    (assert_fps_mean_stable); the others sample for hold_s seconds (assert_fps_stable). The Aggregate FPS plot
    value is printed for information only.

    Args:
        page (Page): Playwright page.
        filename (str): Image to pick in the Add file dialog.
        steps (list[int]): Target FPS values, in order; the first is used when adding the source.
        settle_s (float): Seconds to wait after each change before sampling.
        hold_s (float): Seconds to sample for the non-ceiling steps.
        tolerance_frac (float): Allowed relative deviation from the target.

    Returns:
        list[str]: Failure messages for the steps that did not hold.
    """
    print(f'clicking Add file -> {filename}')
    page.get_by_role('button', name='Add file', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=5000)
    dialog.locator('.q-field').filter(has_text='File / folder').click()
    option = page.locator('.q-menu .q-item').filter(has_text=filename).first
    option.wait_for(state='visible', timeout=5000)
    option.click()
    fps_input = dialog.locator('.q-field').filter(has_text='FPS').locator('input')
    fps_input.fill(str(steps[0]))
    dialog.get_by_role('button', name='Open', exact=True).click()
    dialog.wait_for(state='hidden', timeout=5000)
    print(f'PASS: added {filename!r} at {steps[0]} FPS')

    failures = []
    target_fps_input = page.locator('.target-fps-input input').first
    for i, target in enumerate(steps):
        if i > 0:
            print(f'retargeting live source to {target} FPS')
            target_fps_input.fill(str(target))
            target_fps_input.press('Tab')
        is_ceiling = target == max(steps)
        label = f'{target} FPS step' + (' (ramp ceiling -- must stay stable)' if is_ceiling else '')
        try:
            if is_ceiling:
                print(f'performance gate (mean-gated): after a {settle_s:.0f}s settle, sampling raw '
                      f'infer_fps until >=500 readings are collected to confirm the pipeline SUSTAINS '
                      f'{target} FPS on average, not just per-sample')
                mean_fps = assert_fps_mean_stable(page, target, settle_s=settle_s, label=label)
            else:
                print(f'performance gate: after a {settle_s:.0f}s settle, sampling raw infer_fps every 2s for '
                      f'{hold_s:.0f}s to confirm the pipeline SUSTAINS {target} FPS, not just touches it once')
                mean_fps = assert_fps_stable(
                    page, target * (1 - tolerance_frac), ceiling_fps=target * (1 + tolerance_frac),
                    settle_s=settle_s, hold_s=hold_s, label=label)
        except RuntimeError as exc:
            failures.append(str(exc))
            print(f'FAIL: {exc}', file=sys.stderr)
            continue
        agg = _read_aggregate_fps(page)
        agg_str = f'{agg:.1f}' if agg is not None else 'n/a'
        print(f'(informational, not gated) Aggregate FPS Plotly trace reads {agg_str} while '
              f'raw infer_fps held at mean {mean_fps:.1f} for target {target}')
    return failures


def main() -> int:
    """Run the whole two-stage cascade release test and print a summary.

    Prepares the host with both models, configures the wizard, picks a device that is healthy for both stages
    (retrying on device faults), launches the pipeline, then ramps benchmark FPS and removes the source.
    Page errors count as failures. Saves a final screenshot under tests/.

    Returns:
        int: 0 if all steps passed, 1 otherwise.
    """
    prepare_host([PRIMARY_MODEL, SECONDARY_MODEL])
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page_errors = []
        console_errors = []
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)

        print(f'--- loading {BASE_URL} ---')
        page.goto(BASE_URL, wait_until='networkidle')

        try:
            page.get_by_text('Pipeline Editor', exact=True).click()
            page.wait_for_selector('.vue-flow__pane', state='visible', timeout=15000)

            force_stop_all(page)

            def configure_wizard():
                dialog = open_two_stage_cascade_wizard(page)
                configure_stage(page, dialog, 'Primary model', PRIMARY_MODEL, 1, 'det')
                configure_stage(page, dialog, 'Secondary model', SECONDARY_MODEL, 3, 'pose')

                filter_classes = dialog.locator('.q-field:visible').filter(
                    has_text='classes (optional').locator('input')
                filter_classes.fill('0')
                print('PASS: Filter classes set to 0')

                imdecode_input = dialog.locator('.q-field:visible').filter(
                    has_text='imdecode_threads override').locator('input')
                imdecode_input.fill('16')
                imdecode_input.press('Tab')
                print('PASS: imdecode_threads override set to 16')
                return dialog

            dialog = configure_wizard()
            health_text = run_health_check(dialog)
            candidates = healthy_device_candidates(health_text, STAGE_LABELS)
            if not candidates:
                raise RuntimeError(f'no single device is healthy for every stage of this cascade -- '
                                    f'not a go:\n{health_text}')
            print(f'PASS: candidate device(s) to try, in order: {candidates}')

            tried = []
            launched_text = failed_text = None
            for i, device in enumerate(candidates):
                tried.append(device)
                if i > 0:
                    force_stop_all(page)
                    dialog = configure_wizard()
                if device != 0:
                    select_device(page, dialog, 'Primary model', device, 1)
                    select_device(page, dialog, 'Secondary model', device, 3)
                generate_pipeline(page, dialog)
                ensure_opencl_disabled(page)
                generate_config_yaml(page)
                launched_text, failed_text = compile_and_launch_vision(page)
                if failed_text and any(sig in failed_text for sig in DEVICE_FAULT_SIGNATURES):
                    print(f'device {device} faulted at compile time -- '
                          f'{len(candidates) - len(tried)} candidate(s) left to try')
                    continue
                break

            if failed_text and any(sig in failed_text for sig in DEVICE_FAULT_SIGNATURES):
                failures.append(f'every candidate device faulted at compile time: {tried} (last: {failed_text})')
                print(f'FAIL: every candidate device faulted at compile time: {tried}')
            elif failed_text:
                failures.append(failed_text)
                print(f'FAIL: {failed_text}')
            elif launched_text:
                print(f'PASS: {launched_text}')
            else:
                failures.append('Compile and Launch Pipeline produced neither a launch-success nor '
                                 'launch-failed notification')

            print('switching to Benchmarking tab')
            page.get_by_text('Benchmarking', exact=True).click()
            page.wait_for_timeout(500)

            print('removing any pre-existing benchmark sources (defensive cleanup)')
            _remove_all_benchmark_sources(page)

            print('hovering the Advanced Settings edge sensor to reveal the drawer')
            page.locator('[aria-label="benchmark settings edge"]').hover()
            switch = page.get_by_text('AIMD backoff', exact=True).locator('xpath=ancestor::div[@role="switch"]').first
            switch.wait_for(state='visible', timeout=5000)
            if switch.get_attribute('aria-checked') != 'false':
                switch.click()
                page.wait_for_timeout(300)
            if switch.get_attribute('aria-checked') != 'false':
                raise RuntimeError('failed to disable AIMD backoff')
            print('PASS: AIMD backoff disabled')

            bp_field = page.locator('.q-field').filter(has_text='Backpressure cap').locator('input')
            bp_field.fill(str(BACKPRESSURE_CAP))
            bp_field.press('Tab')
            print(f'PASS: Backpressure cap set to {BACKPRESSURE_CAP}')

            enable_monitor_checkboxes(page)

            ramp_failures = add_benchmark_source_and_ramp(
                page, BENCHMARK_IMAGE_FILENAME, FPS_STEPS,
                FPS_GATE_SETTLE_S, FPS_GATE_HOLD_S, FPS_GATE_TOLERANCE_FRAC)
            failures.extend(ramp_failures)

            print('cleaning up: removing the benchmark source so it does not contend with later runs')
            _remove_all_benchmark_sources(page)
            print('PASS: removed benchmark source(s) (cleanup)')
        except Exception as exc:
            print(f'FAIL: {exc}', file=sys.stderr)
            failures.append(str(exc))

        print('--- page errors ---')
        for e in page_errors:
            print(e)
            failures.append(f'page error: {e}')
        print('--- console errors (recent) ---')
        for e in console_errors[-20:]:
            print(e)

        page.screenshot(path='tests/_release_playwright_cascade_final.png', full_page=True)
        browser.close()

    print('\n=== SUMMARY ===')
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        print('test_release_playwright_cascade: FAIL')
        return 1
    print('ALL STEPS PASSED')
    print('test_release_playwright_cascade: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
