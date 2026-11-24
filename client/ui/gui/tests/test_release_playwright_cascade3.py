#!/usr/bin/env python3
"""Release test that builds the Three-Stage Conditional Cascade example in the GUI with Playwright, launches it and checks it sustains the target FPS.

Takes an optional base URL as the first command-line argument (default http://127.0.0.1:8090).
"""

import sys
from utils.host_server_prep import prepare_host

from playwright.sync_api import sync_playwright

from test_release_playwright_isovision import (
    force_stop_all,
    ensure_opencl_disabled,
    generate_config_yaml,
    compile_and_launch_vision,
    _remove_all_benchmark_sources,
    assert_fps_stable_with_retry,
    assert_fps_mean_stable,
)
from test_release_playwright_cascade import (
    select_option,
    select_device,
    healthy_device_candidates,
    DEVICE_FAULT_SIGNATURES,
    enable_monitor_checkboxes,
    _read_aggregate_fps,
    MONITOR_CHECKBOX_LABELS,
)

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090'
PRIMARY_MODEL = 'yolox-m-coco-onnx'
SECONDARY_MODEL = 'yolo26npose-coco-onnx'
TERTIARY_MODEL = 'retinaface-mobilenet0.25-widerface-onnx'
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
BACKPRESSURE_CAP = 1000
FPS_STEPS = [5, 10, 15, 30]
FPS_GATE_SETTLE_S = 2.0
FPS_GATE_HOLD_S = 8.0
FPS_GATE_TOLERANCE_FRAC = 0.15
FPS_GATE_MAX_RETRIES = 2
FPS_GATE_HOLD_GROWTH = 2.0
STAGE_LABELS = ['Primary model', 'Secondary model', 'Conditional tertiary model']


def open_three_stage_cascade_wizard(page):
    """Expand the Examples palette category and open the Three-Stage Conditional Cascade dialog.

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
    tree.get_by_text('Three-Stage Conditional Cascade', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=10000)
    print('PASS: Three-Stage Conditional Cascade dialog opened')
    return dialog


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


def configure_stage(page, dialog, stage_label, model_name, cores, meta_key, download_timeout_s=300.0):
    """Select the model of one stage and set its meta_key_override and core count in the cascade dialog.

    Uses the model from the "Model (.axnet, from host server)" dropdown when listed there, otherwise falls back
    to "Use prebuilt models" and waits for the selected model to be reported as downloaded.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        stage_label (str): Stage name; for other than 'Primary model' its tab is clicked first.
        model_name (str): Model to select.
        cores (int): Value for the "Cores on Device 0" field.
        meta_key (str): Value for meta_key_override.
        download_timeout_s (float, optional): Seconds to wait for a prebuilt download. Defaults to 300.0.

    Raises:
        RuntimeError: If the prebuilt checkbox or model is not found, or the download fails or times out.
    """
    if stage_label != 'Primary model':
        dialog.get_by_text(stage_label, exact=True).click()
        page.wait_for_timeout(300)

    build_field = dialog.locator('.q-field:visible').filter(has_text='Model (.axnet, from host server)')
    current = build_field.inner_text()
    if model_name in current:
        print(f'PASS: {stage_label}: {model_name!r} already selected under $SDK_ROOT/build')
    else:
        build_field.click()
        option = page.locator('.q-menu .q-item').filter(has_text=model_name).first
        try:
            option.wait_for(state='visible', timeout=3000)
            option.click()
            page.wait_for_timeout(300)
            print(f'PASS: {stage_label}: selected {model_name!r} from the $SDK_ROOT/build dropdown')
        except Exception:
            page.keyboard.press('Escape')
            print(f'{stage_label}: {model_name!r} not available under $SDK_ROOT/build -- '
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

            deadline = __import__('time').time() + download_timeout_s
            downloaded = False
            while __import__('time').time() < deadline:
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
                raise RuntimeError(f'prebuilt model {model_name!r} did not finish downloading '
                                    f'within {download_timeout_s}s')
            print(f'PASS: {stage_label}: {model_name!r} downloaded')

    meta_input = dialog.locator('.q-field:visible').filter(has_text='meta_key_override').locator('input')
    meta_input.fill(meta_key)
    cores_field = dialog.locator('.q-field:visible').filter(has_text='Cores on Device 0').locator('input')
    cores_field.fill(str(cores))
    cores_field.press('Tab')
    print(f'PASS: {stage_label} set to {model_name}, device 0, {cores} core(s), meta_key_override={meta_key}')


def configure_condition(page, dialog, meta_key, indices, value):
    """Set the tertiary stage condition to kpts_conf_gt with the given predicate parameters.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The cascade dialog.
        meta_key (str): Value for "predicate meta_key".
        indices (str): Comma-separated keypoint indices.
        value (float): Confidence threshold.
    """
    type_select = dialog.locator('.q-field:visible').filter(has_text='type').first
    select_option(page, type_select, 'kpts_conf_gt')

    meta_key_label = dialog.locator(':visible').get_by_text('predicate meta_key', exact=True)
    predicate_meta_key = meta_key_label.locator(
        'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " q-field ")][1]//input'
    )
    predicate_meta_key.fill(meta_key)

    predicate_indices = dialog.locator('.q-field:visible').filter(
        has_text='indices (comma-separated, e.g. 0,1,2)').locator('input')
    predicate_indices.fill(indices)

    predicate_value = dialog.locator('.q-field:visible').filter(
        has_text='value (confidence threshold)').locator('input')
    predicate_value.fill(str(value))
    print(f'PASS: condition set to kpts_conf_gt(meta_key={meta_key}, indices={indices}, value={value}) '
          '(predicate name left at its default "roi_gate")')


def run_health_check(dialog, expected_stages=3, timeout_s=240.0):
    """Click Run Health Check (all models) in the dialog and wait until every stage reports a result.

    Args:
        dialog (Locator): The cascade dialog.
        expected_stages (int, optional): Number of result lines to wait for. Defaults to 3.
        timeout_s (float, optional): Seconds to wait. Defaults to 240.0.

    Returns:
        str: The health result text.

    Raises:
        RuntimeError: If the result says the health check failed.
    """
    import time
    print('clicking Run Health Check (all models)')
    dialog.get_by_text('Run Health Check (all models)', exact=True).click()
    health_label = dialog.locator('.text-caption.text-grey-7').first
    deadline = time.time() + timeout_s
    last_text = ''
    while time.time() < deadline:
        last_text = health_label.inner_text()
        lines = [l for l in last_text.split('\n') if l.strip()]
        if lines and all('Checking' not in l for l in lines) and len(lines) >= expected_stages:
            break
        time.sleep(2.0)
    print(f'health check result:\n{last_text}')
    if 'health check failed' in last_text.lower():
        raise RuntimeError(f'health check failed: {last_text}')
    print(f'PASS: health check -- all {expected_stages} stages reported')
    return last_text


def generate_pipeline(page, dialog):
    """Click Generate Pipeline, wait for the dialog to close and print the resulting canvas node texts."""
    print('clicking Generate Pipeline')
    dialog.get_by_text('Generate Pipeline', exact=True).click()
    dialog.wait_for(state='hidden', timeout=10000)
    page.wait_for_timeout(500)
    node_texts = page.locator('.vue-flow__node').all_inner_texts()
    print(f'PASS: Generate Pipeline closed the dialog -- canvas nodes: {node_texts}')


def add_benchmark_source_and_sweep(page, filename, steps, settle_s, hold_s, tolerance_frac, max_retries, hold_growth):
    """Add an image benchmark source and step its target FPS through the given values, gating each step.

    Every step checks that raw infer_fps holds near the target, with retries and a longer hold on each retry
    (assert_fps_stable_with_retry). The highest step uses the mean-based gate (assert_fps_mean_stable). The
    Aggregate FPS plot value is printed for information only.

    Args:
        page (Page): Playwright page.
        filename (str): Image to pick in the Add file dialog.
        steps (list[int]): Target FPS values, in order; the first is used when adding the source.
        settle_s (float): Seconds to wait after each change before sampling.
        hold_s (float): Initial sampling duration for the non-ceiling steps.
        tolerance_frac (float): Allowed relative deviation from the target.
        max_retries (int): Extra attempts per non-ceiling step.
        hold_growth (float): Factor applied to the hold on each retry.

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
        label = f'{target} FPS step' + (' (sweep ceiling -- must stay stable)' if is_ceiling else '')
        try:
            if is_ceiling:
                print(f'performance gate (mean-gated): after a {settle_s:.0f}s settle, sampling raw '
                      f'infer_fps until >=500 readings are collected to confirm the pipeline SUSTAINS '
                      f'{target} FPS on average, not just per-sample')
                mean_fps = assert_fps_mean_stable(page, target, settle_s=settle_s, label=label)
            else:
                print(f'performance gate: after a {settle_s:.0f}s settle, sampling raw infer_fps every 2s for '
                      f'~{hold_s:.0f}s (longer on retry) to confirm the pipeline SUSTAINS {target} FPS, not just '
                      f'touches it once')
                mean_fps = assert_fps_stable_with_retry(
                    page, target * (1 - tolerance_frac), ceiling_fps=target * (1 + tolerance_frac),
                    settle_s=settle_s, hold_s=hold_s, max_retries=max_retries, hold_growth=hold_growth, label=label)
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
    """Run the whole three-stage cascade release test and print a summary.

    Prepares the host with all three models, configures the wizard including the condition, picks a device that is
    healthy for every stage (retrying on device faults), launches the pipeline, then sweeps benchmark FPS and removes
    the source. Page errors count as failures. Saves a final screenshot under tests/.

    Returns:
        int: 0 if all steps passed, 1 otherwise.
    """
    prepare_host([PRIMARY_MODEL, SECONDARY_MODEL, TERTIARY_MODEL])
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
                dialog = open_three_stage_cascade_wizard(page)
                configure_stage(page, dialog, 'Primary model', PRIMARY_MODEL, 1, 'det')
                configure_stage(page, dialog, 'Secondary model', SECONDARY_MODEL, 2, 'pose')
                configure_stage(page, dialog, 'Conditional tertiary model', TERTIARY_MODEL, 1, 'face')
                configure_condition(page, dialog, meta_key='pose', indices='0,1,2', value=0.5)

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
            health_text = run_health_check(dialog, expected_stages=3)
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
                    select_device(page, dialog, 'Secondary model', device, 2)
                    select_device(page, dialog, 'Conditional tertiary model', device, 1)
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

            sweep_failures = add_benchmark_source_and_sweep(
                page, BENCHMARK_IMAGE_FILENAME, FPS_STEPS, FPS_GATE_SETTLE_S, FPS_GATE_HOLD_S,
                FPS_GATE_TOLERANCE_FRAC, FPS_GATE_MAX_RETRIES, FPS_GATE_HOLD_GROWTH)
            failures.extend(sweep_failures)

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

        page.screenshot(path='tests/_release_playwright_cascade3_final.png', full_page=True)
        browser.close()

    print('\n=== SUMMARY ===')
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        print('test_release_playwright_cascade3: FAIL')
        return 1
    print('ALL STEPS PASSED')
    print('test_release_playwright_cascade3: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
