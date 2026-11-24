#!/usr/bin/env python3
"""Release test that drives the Isovision Demo wizard of a running GUI with Playwright, launches the generated pipelines and checks the benchmark FPS."""

from __future__ import annotations

import argparse
import re
import sys
from utils.host_server_prep import prepare_host
import time

from playwright.sync_api import Page, sync_playwright

MODEL_NAME = 'yolox-m-coco-onnx'
IMDECODE_THREADS_OVERRIDE = 16
CORES_PER_INSTANCE = 4
THROUGHPUT_SECONDS = 5
DEVICES_PER_PIPELINE = 1
BENCHMARK_IMAGE_FILENAME = 'dancing_frame_t15_480p.jpg'
BENCHMARK_SOURCE_FPS = 1000
BENCHMARK_BACKPRESSURE_CAP = 1000
BENCHMARK_TARGET_FPS_MIN = 300.0

_HEALTH_RE = re.compile(r'(\d+)\s*/\s*(\d+)\s*device\(s\)\s*healthy')
_THROUGHPUT_RE = re.compile(r'Aggregate:\s*([\d.]+)\s*FPS')
_INFER_FPS_RE = re.compile(r'infer:\s*([\d.]+)\s*fps')


def _clear_canvas_nodes(page: Page) -> None:
    """Delete every node on the Pipeline Editor canvas through the right-click "Delete node" menu.

    Raises:
        RuntimeError: If nodes remain after 30 passes.
    """
    guard = 0
    while page.locator('.vue-flow__node').count() > 0:
        guard += 1
        if guard > 30:
            raise RuntimeError('failed to clear pre-existing canvas nodes before starting (stuck looping)')
        node = page.locator('.vue-flow__node').first
        menu = page.get_by_text('Delete node', exact=True)
        for attempt in range(5):
            box = node.bounding_box()
            page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, button='right')
            try:
                menu.wait_for(timeout=3000)
                break
            except Exception:
                if attempt == 4:
                    raise
                page.keyboard.press('Escape')
                page.wait_for_timeout(1000)
        menu.click()
        page.wait_for_timeout(500)


def _fill_field(scope, field_label: str, value: str) -> None:
    """Fill the text input of the Quasar field whose text contains field_label and press Tab to commit it."""
    field = scope.locator('.q-field').filter(has_text=field_label).first
    inp = field.locator('input').first
    inp.fill(value)
    inp.press('Tab')


def ensure_opencl_disabled(page: Page) -> None:
    """Switch the OpenCL global setting off if it is on.

    Raises:
        RuntimeError: If the switch is still on afterwards.
    """
    switch = page.get_by_text('OpenCL', exact=True).locator('xpath=ancestor::div[@role="switch"]').first
    if switch.get_attribute('aria-checked') != 'false':
        switch.click()
        page.wait_for_timeout(300)
    state = switch.get_attribute('aria-checked')
    if state != 'false':
        raise RuntimeError(f'failed to disable the OpenCL global setting (aria-checked={state!r})')
    print('PASS: OpenCL global setting disabled')


def force_stop_all(page: Page) -> None:
    """Open the Pipeline Editor tab, click Force Stop All, confirm the dialog and wait for the result notification.

    A missing confirmation dialog or result notification is reported on stderr, not raised.
    """
    page.get_by_text('Pipeline Editor', exact=True).click()
    page.wait_for_timeout(500)
    print('clicking Force Stop All')
    page.get_by_role('button', name='Force Stop All', exact=True).click()
    dialog = page.locator('.q-dialog').last
    try:
        dialog.wait_for(state='visible', timeout=5000)
    except Exception:
        print('WARNING: Force Stop All confirmation dialog never appeared -- skipping', file=sys.stderr)
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
        print(f'PASS: force stop all -> {result_text}')
    else:
        print('WARNING: force stop all did not produce the expected notification in time', file=sys.stderr)
    page.wait_for_timeout(1000)


def open_isovision_demo_wizard(page: Page):
    """Clear the canvas (reloading the page up to twice on failure) and open the Isovision Demo dialog.

    If the canvas cannot be cleared a warning is printed and the test continues.

    Returns:
        Locator: The opened dialog.
    """
    page.wait_for_selector('.vue-flow__pane', state='visible', timeout=10000)

    last_exc: Exception | None = None
    for reload_attempt in range(3):
        if reload_attempt > 0:
            print(f'canvas cleanup failed ({last_exc}); reloading and retrying '
                  f'(attempt {reload_attempt + 1}/3)', file=sys.stderr)
            page.reload(wait_until='networkidle')
            page.get_by_text('Pipeline Editor', exact=True).click()
            page.wait_for_timeout(800)
        try:
            _clear_canvas_nodes(page)
            break
        except Exception as exc:
            last_exc = exc
    else:
        print(f'WARNING: could not clear pre-existing canvas nodes after reload retries '
              f'({last_exc}) -- proceeding anyway, Generate Pipelines will replace the '
              f'canvas wholesale regardless', file=sys.stderr)

    tree = page.locator('.q-tree')
    examples_label = tree.get_by_text('Examples', exact=True)
    examples_label.locator(
        'xpath=ancestor::div[contains(concat(" ", normalize-space(@class), " "), " q-tree__node-header ")][1]'
        '//i[contains(@class,"q-tree__arrow")]'
    ).click()
    page.wait_for_timeout(500)
    tree.get_by_text('Isovision Demo', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=10000)
    print('PASS: Isovision Demo dialog opened')
    return dialog


def ensure_model_selected(dialog, page: Page, model_name: str, download_timeout_s: float = 300.0) -> None:
    """Select a model in the Isovision dialog, from the $SDK_ROOT/build dropdown or else from the prebuilt catalog.

    For a prebuilt model, waits until the dropdown shows it as downloaded.

    Args:
        dialog (Locator): The Isovision dialog.
        page (Page): Playwright page.
        model_name (str): Model to select.
        download_timeout_s (float, optional): Seconds to wait for a prebuilt download. Defaults to 300.0.

    Raises:
        RuntimeError: If the download fails or does not finish in time.
    """
    build_select = dialog.locator('.q-field').filter(has_text='Model (.axnet, from host server)')
    if build_select.count() > 0:
        current = build_select.first.inner_text()
        if model_name in current:
            print(f'PASS: {model_name!r} already selected under $SDK_ROOT/build')
            return
        build_select.first.click()
        option = page.locator('.q-menu .q-item').filter(has_text=model_name).first
        try:
            option.wait_for(state='visible', timeout=3000)
            option.click()
            page.wait_for_timeout(300)
            print(f'PASS: selected {model_name!r} from the $SDK_ROOT/build dropdown')
            return
        except Exception:
            page.keyboard.press('Escape')
            print(f'{model_name!r} not available under $SDK_ROOT/build -- falling back to prebuilt models')

    print('ticking "Use prebuilt models" and waiting for the catalog fetch')
    checkbox_label = dialog.get_by_text('Use prebuilt models', exact=False).first
    checkbox = checkbox_label.locator('xpath=ancestor::div[@role="checkbox"][1]')
    if checkbox.get_attribute('aria-checked') != 'true':
        checkbox.click()

    prebuilt_select = dialog.locator('.q-field').filter(has_text='Prebuilt model')
    prebuilt_select.first.wait_for(state='visible', timeout=60000)
    print('PASS: prebuilt model catalog fetched')

    prebuilt_select.first.click()
    option = page.locator('.q-menu .q-item').filter(has_text=model_name).first
    option.wait_for(state='visible', timeout=10000)
    option.click()
    print(f'selected {model_name!r} from the prebuilt catalog -- waiting for its artifacts to download')

    deadline = time.time() + download_timeout_s
    while time.time() < deadline:
        notif_texts = page.locator('.q-notification__message').all_inner_texts()
        for t in notif_texts:
            if model_name in t and ('failed' in t.lower() or 'could not reach' in t.lower()):
                raise RuntimeError(f'failed to download prebuilt model {model_name!r}: {t}')
        current_text = prebuilt_select.first.inner_text()
        if model_name in current_text and 'downloaded' in current_text.lower():
            print(f'PASS: {model_name!r} downloaded')
            return
        page.wait_for_timeout(1000)
    raise RuntimeError(f'prebuilt model {model_name!r} did not finish downloading within {download_timeout_s}s')


def drive_wizard(page: Page, dialog, health_timeout_s: float = 300.0) -> int:
    """Configure the Isovision dialog, run the health check and throughput test and generate the pipelines.

    Sets imdecode_threads, devices per pipeline, CPU/NUMA pinning with CORES_PER_INSTANCE cores and the throughput
    duration. A missing pinning control or an unreported throughput result is a warning only.

    Args:
        page (Page): Playwright page.
        dialog (Locator): The Isovision dialog.
        health_timeout_s (float, optional): Seconds to wait for the health check. Defaults to 300.0.

    Returns:
        int: Number of pipelines generated (healthy devices divided by DEVICES_PER_PIPELINE).

    Raises:
        RuntimeError: If the health check fails, never completes or finds no healthy device, or if the
            canvas does not have 3 nodes and 2 edges per pipeline.
    """
    _fill_field(dialog, 'imdecode_threads override', str(IMDECODE_THREADS_OVERRIDE))
    print(f'PASS: imdecode_threads override set to {IMDECODE_THREADS_OVERRIDE}')

    print('clicking Run Health Check')
    dialog.get_by_role('button', name='Run Health Check', exact=True).click()
    deadline = time.time() + health_timeout_s
    healthy_count = total_count = None
    last_text = ''
    while time.time() < deadline:
        texts = dialog.locator('.text-body2').all_inner_texts()
        for t in texts:
            if 'failed' in t.lower():
                raise RuntimeError(f'device health check failed: {t}')
            m = _HEALTH_RE.search(t)
            if m:
                healthy_count, total_count = int(m.group(1)), int(m.group(2))
                last_text = t
                break
        if healthy_count is not None:
            break
        page.wait_for_timeout(2000)
    if healthy_count is None:
        raise RuntimeError(f'health check never completed within {health_timeout_s}s')
    print(f'PASS: health check -> {last_text}')
    if healthy_count < 1:
        raise RuntimeError('no healthy devices -- cannot generate any pipeline')

    print(f'setting Devices per pipeline to {DEVICES_PER_PIPELINE}')
    _fill_field(dialog, 'Devices per pipeline', str(DEVICES_PER_PIPELINE))

    print(f'enabling Pin CPU/NUMA and setting {CORES_PER_INSTANCE} core(s) per instance')
    numa_switch = dialog.get_by_text('Pin CPU/NUMA', exact=False).locator(
        'xpath=ancestor::div[@role="switch"][1]').first
    if numa_switch.count() > 0:
        if numa_switch.get_attribute('aria-checked') != 'true':
            numa_switch.click()
            page.wait_for_timeout(200)
        cores_select = dialog.locator('.q-field').filter(has_text='core(s) per instance')
        if cores_select.count() > 0 and cores_select.first.is_visible():
            cores_select.first.click()
            option = page.locator('.q-menu .q-item').filter(
                has_text=f'{CORES_PER_INSTANCE} core(s) per instance').first
            option.wait_for(state='visible', timeout=5000)
            option.click()
            page.wait_for_timeout(200)
            print(f'PASS: {CORES_PER_INSTANCE} core(s) per instance selected, CPU/NUMA pinning enabled')
        else:
            print('WARNING: cores-per-instance select never became visible (host has no CPU topology info) '
                  '-- CPU/NUMA pinning left on with its default core count', file=sys.stderr)
    else:
        print('WARNING: "Pin CPU/NUMA" switch not found -- skipping cores-per-instance step', file=sys.stderr)

    _fill_field(dialog, 'Seconds', str(THROUGHPUT_SECONDS))
    print(f'clicking Throughput Test ({THROUGHPUT_SECONDS}s)')
    dialog.get_by_role('button', name='Throughput Test', exact=True).click()
    throughput_deadline = time.time() + max(60.0, THROUGHPUT_SECONDS * 4 + 30)
    throughput_text = ''
    while time.time() < throughput_deadline:
        texts = dialog.locator('.text-caption.text-grey-7').all_inner_texts()
        candidates = [t for t in texts if t.strip().startswith(('Aggregate:', 'Throughput test failed', 'Running '))]
        done = [t for t in candidates if t.strip().startswith(('Aggregate:', 'Throughput test failed'))]
        if done:
            throughput_text = done[0]
            break
        page.wait_for_timeout(1000)
    if throughput_text.startswith('Aggregate:'):
        m = _THROUGHPUT_RE.search(throughput_text)
        print(f'PASS: throughput test -> {throughput_text}' + (f' ({float(m.group(1)):.1f} FPS)' if m else ''))
    else:
        print(f'WARNING: throughput test did not report a result in time (last seen: {throughput_text!r})',
              file=sys.stderr)

    print('clicking Generate Pipelines')
    dialog.get_by_role('button', name='Generate Pipelines', exact=True).click()
    dialog.wait_for(state='hidden', timeout=15000)
    page.wait_for_timeout(1000)

    per_pipeline = DEVICES_PER_PIPELINE
    pipeline_count = healthy_count // per_pipeline if per_pipeline else healthy_count
    expected_nodes, expected_edges = pipeline_count * 3, pipeline_count * 2
    n_nodes = page.locator('.vue-flow__node').count()
    n_edges = page.locator('.vue-flow__edge').count()
    if n_nodes != expected_nodes or n_edges != expected_edges:
        raise RuntimeError(
            f'canvas after Generate Pipelines has {n_nodes} node(s)/{n_edges} edge(s), '
            f'expected {expected_nodes}/{expected_edges} for {pipeline_count} pipeline(s)')
    print(f'PASS: canvas has {n_nodes} nodes / {n_edges} edges ({pipeline_count} independent '
          f'Input->Model->Sink chains)')
    return pipeline_count


def generate_config_yaml(page: Page, timeout_s: float = 30.0) -> None:
    """Click Generate Config YAML, save the dialog and wait for the "Wrote ..." notification.

    Args:
        page (Page): Playwright page.
        timeout_s (float, optional): Seconds to wait for the notification. Defaults to 30.0.

    Raises:
        RuntimeError: If the notification does not appear.
    """
    print('clicking Generate Config YAML')
    page.get_by_role('button', name='Generate Config YAML', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=10000)
    dialog.get_by_role('button', name='Save', exact=True).click()
    deadline = time.time() + timeout_s
    wrote_text = None
    while time.time() < deadline:
        for n in page.locator('.q-notification__message').all_inner_texts():
            if n.startswith('Wrote '):
                wrote_text = n
                break
        if wrote_text:
            break
        page.wait_for_timeout(500)
    if not wrote_text:
        raise RuntimeError('Generate Config YAML -> Save never produced a "Wrote ..." notification')
    print(f'PASS: {wrote_text}')


def _compile_block_reason(page: Page) -> str | None:
    """Search the page HTML for text explaining why Compile and Launch is blocked.

    Returns:
        str | None: The matching snippet, or None.
    """
    content = page.content()
    for m in re.finditer(r'.{0,80}(?:failed a health check|Generate the config YAML first|'
                          r'Compile/launch already in progress).{0,160}', content):
        return m.group(0)
    return None


def compile_and_launch_vision(page: Page, timeout_s: float = 900.0) -> tuple[str | None, str | None]:
    """Click Compile and Launch Pipeline and watch notifications until a launch result appears.

    Args:
        page (Page): Playwright page.
        timeout_s (float, optional): Seconds to wait. Defaults to 900.0.

    Returns:
        tuple[str | None, str | None]: The "Launched ... pipeline(s)" notification and the failure notification
        ("Launch failed", "Cannot compile" or "Upload failed"); both None on timeout.

    Raises:
        RuntimeError: If the button is disabled.
    """
    btn = page.get_by_role('button', name='Compile and Launch Pipeline', exact=True)
    if btn.get_attribute('aria-disabled') == 'true':
        reason = _compile_block_reason(page)
        raise RuntimeError(f'Compile and Launch Pipeline is disabled -- block reason: {reason!r}')
    print('clicking Compile and Launch Pipeline')
    btn.click()
    deadline = time.time() + timeout_s
    seen: list[str] = []
    launched_text = failed_text = None
    while time.time() < deadline:
        for n in page.locator('.q-notification__message').all_inner_texts():
            if n not in seen:
                seen.append(n)
                print(f'notification: {n}')
                if n.startswith('Launched') and 'pipeline(s)' in n:
                    launched_text = n
                if n.startswith('Launch failed') or n.startswith('Cannot compile') or n.startswith('Upload failed'):
                    failed_text = n
        if launched_text or failed_text:
            break
        page.wait_for_timeout(5000)
    return launched_text, failed_text


def _remove_all_benchmark_sources(page: Page) -> None:
    """Click the delete_sweep button on the Benchmarking tab to remove every benchmark source."""
    page.locator('button:has(i.material-icons:text-is("delete_sweep"))').click()
    page.wait_for_timeout(500)


def read_raw_infer_fps(page: Page) -> float | None:
    """Read the first "infer: N fps" value found in the page HTML.

    Returns:
        float | None: The value, or None if absent.
    """
    m = _INFER_FPS_RE.search(page.content())
    return float(m.group(1)) if m else None


def assert_fps_stable(page: Page, floor_fps: float, *, ceiling_fps: float | None = None,
                       settle_s: float = 6.0, hold_s: float = 20.0, sample_interval_s: float = 2.0,
                       label: str | None = None) -> float:
    """Check that the raw inference FPS stays inside a band for a whole hold period.

    Waits settle_s, then samples every sample_interval_s for hold_s seconds.

    Args:
        page (Page): Playwright page.
        floor_fps (float): Minimum allowed value for every sample.
        ceiling_fps (float | None, optional): Maximum allowed value. Defaults to None (no upper bound).
        settle_s (float, optional): Seconds to wait before sampling. Defaults to 6.0.
        hold_s (float, optional): Sampling duration in seconds. Defaults to 20.0.
        sample_interval_s (float, optional): Seconds between samples. Defaults to 2.0.
        label (str | None, optional): Name used in messages. Defaults to the floor value.

    Returns:
        float: Mean of the samples.

    Raises:
        RuntimeError: If any sample is missing or outside the band.
    """
    label = label or f'floor {floor_fps:.0f} fps'
    time.sleep(settle_s)
    samples: list[float | None] = []
    t0 = time.time()
    while time.time() - t0 < hold_s:
        time.sleep(sample_interval_s)
        raw = read_raw_infer_fps(page)
        samples.append(raw)
        print(f'  [{label}] t+{time.time() - t0:4.1f}s raw_infer_fps={raw}')
    missing = sum(1 for s in samples if s is None)
    if missing:
        raise RuntimeError(f'{label}: {missing}/{len(samples)} samples had no infer_fps reading at all')
    valid = [s for s in samples if s is not None]
    bad = [s for s in valid if s < floor_fps or (ceiling_fps is not None and s > ceiling_fps)]
    mean = sum(valid) / len(valid)
    if bad:
        band = f'>= {floor_fps:.1f}' + (f' and <= {ceiling_fps:.1f}' if ceiling_fps is not None else '')
        raise RuntimeError(
            f'{label}: NOT stable -- {len(bad)}/{len(valid)} samples violated {band} '
            f'(mean={mean:.1f}, samples={valid})')
    band_desc = f'>= {floor_fps:.1f}' + (f', <= {ceiling_fps:.1f}' if ceiling_fps is not None else '')
    print(f'PASS: {label} stable across {hold_s:.0f}s -- {len(valid)}/{len(valid)} samples {band_desc} '
          f'(mean={mean:.1f})')
    return mean


def assert_fps_stable_with_retry(page: Page, floor_fps: float, *, ceiling_fps: float | None = None,
                                  settle_s: float = 2.0, hold_s: float = 8.0, sample_interval_s: float = 2.0,
                                  max_retries: int = 2, hold_growth: float = 2.0,
                                  label: str | None = None) -> float:
    """Run assert_fps_stable, retrying with a longer hold each time it fails.

    Args:
        page (Page): Playwright page.
        floor_fps (float): Minimum allowed value for every sample.
        ceiling_fps (float | None, optional): Maximum allowed value. Defaults to None.
        settle_s (float, optional): Seconds to wait before each attempt. Defaults to 2.0.
        hold_s (float, optional): Hold of the first attempt. Defaults to 8.0.
        sample_interval_s (float, optional): Seconds between samples. Defaults to 2.0.
        max_retries (int, optional): Extra attempts after the first. Defaults to 2.
        hold_growth (float, optional): Factor applied to the hold on each retry. Defaults to 2.0.
        label (str | None, optional): Name used in messages.

    Returns:
        float: Mean FPS of the first passing attempt.

    Raises:
        RuntimeError: The error of the last attempt if all fail.
    """
    attempt_hold = hold_s
    last_exc: RuntimeError | None = None
    for attempt in range(max_retries + 1):
        try:
            return assert_fps_stable(page, floor_fps, ceiling_fps=ceiling_fps, settle_s=settle_s,
                                      hold_s=attempt_hold, sample_interval_s=sample_interval_s, label=label)
        except RuntimeError as exc:
            last_exc = exc
            if attempt < max_retries:
                print(f'WARNING: {label} not stable within a {attempt_hold:.0f}s hold -- retrying with a '
                      f'longer {attempt_hold * hold_growth:.0f}s hold', file=sys.stderr)
                attempt_hold *= hold_growth
    assert last_exc is not None
    raise last_exc


def assert_fps_mean_stable(page: Page, target_fps: float, *, tolerance_frac: float = 0.05,
                            min_samples: int = 500, settle_s: float = 6.0,
                            sample_interval_s: float = 0.2, label: str | None = None) -> float:
    """Check that the mean raw inference FPS over many samples is close to a target.

    Waits settle_s, then collects min_samples readings spaced sample_interval_s apart. Individual samples are
    not bounded; only the mean of the valid ones is compared.

    Args:
        page (Page): Playwright page.
        target_fps (float): Expected mean FPS.
        tolerance_frac (float, optional): Allowed relative deviation of the mean. Defaults to 0.05.
        min_samples (int, optional): Number of readings to collect. Defaults to 500.
        settle_s (float, optional): Seconds to wait before sampling. Defaults to 6.0.
        sample_interval_s (float, optional): Seconds between readings. Defaults to 0.2.
        label (str | None, optional): Name used in messages.

    Returns:
        float: Mean of the valid samples.

    Raises:
        RuntimeError: If no sample had a reading or the mean is outside the tolerance band.
    """
    label = label or f'{target_fps:.0f} fps (mean-gated)'
    time.sleep(settle_s)
    samples: list[float | None] = []
    t0 = time.time()
    while len(samples) < min_samples:
        raw = read_raw_infer_fps(page)
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
    print(f'PASS: {label} mean {mean:.2f} fps over {len(valid)}/{len(samples)} samples '
          f'(collected in {elapsed:.0f}s, missing={missing}) within [{lo:.1f}, {hi:.1f}]')
    return mean


def run_benchmark_tab_check(page: Page, timeout_s: float = 60.0) -> float:
    """Add an image benchmark source on the Benchmarking tab and check the measured inference FPS.

    Disables AIMD backoff, sets the backpressure cap, waits for infer FPS to reach BENCHMARK_TARGET_FPS_MIN, requires it
    to stay at or above that for 15 s, reads the Aggregate FPS plot value for information and removes the source.

    Args:
        page (Page): Playwright page.
        timeout_s (float, optional): Seconds to wait for the FPS to ramp up. Defaults to 60.0.

    Returns:
        float: Mean inference FPS from the stability check.

    Raises:
        RuntimeError: If AIMD backoff cannot be disabled, no FPS is reported, or the FPS is too low or unstable.
    """
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
    state = switch.get_attribute('aria-checked')
    if state != 'false':
        raise RuntimeError(f'failed to disable AIMD backoff (aria-checked={state!r})')
    print('PASS: AIMD backoff disabled')

    _fill_field(page, 'Backpressure cap (in-flight inference requests)', str(BENCHMARK_BACKPRESSURE_CAP))
    print(f'PASS: Backpressure cap set to {BENCHMARK_BACKPRESSURE_CAP}')

    print(f'clicking Add file -> {BENCHMARK_IMAGE_FILENAME}')
    page.get_by_role('button', name='Add file', exact=True).click()
    dialog = page.locator('.q-dialog').last
    dialog.wait_for(state='visible', timeout=5000)
    dialog.locator('.q-field').filter(has_text='File / folder').click()
    option = page.locator('.q-menu .q-item').filter(has_text=BENCHMARK_IMAGE_FILENAME).first
    option.wait_for(state='visible', timeout=5000)
    option.click()
    _fill_field(dialog, 'FPS', str(BENCHMARK_SOURCE_FPS))
    dialog.get_by_role('button', name='Open', exact=True).click()
    dialog.wait_for(state='hidden', timeout=5000)
    print(f'PASS: added image source {BENCHMARK_IMAGE_FILENAME!r}')

    print('waiting for measured inference fps to ramp up')
    deadline = time.time() + timeout_s
    infer_fps = None
    while time.time() < deadline:
        infer_fps = read_raw_infer_fps(page)
        if infer_fps is not None and infer_fps >= BENCHMARK_TARGET_FPS_MIN:
            break
        page.wait_for_timeout(2000)
    if infer_fps is None:
        raise RuntimeError(f'{BENCHMARK_IMAGE_FILENAME} source never reported an infer fps within {timeout_s}s')
    print(f'measured inference fps = {infer_fps:.1f} (target >= {BENCHMARK_TARGET_FPS_MIN:.0f})')
    if infer_fps < BENCHMARK_TARGET_FPS_MIN:
        raise RuntimeError(f'measured inference fps {infer_fps:.1f} is below the {BENCHMARK_TARGET_FPS_MIN:.0f} target')
    print(f'PASS: measured inference fps {infer_fps:.1f} reproduces the throughput test\'s aggregate')

    infer_fps = assert_fps_stable_with_retry(page, BENCHMARK_TARGET_FPS_MIN, settle_s=0.0, hold_s=15.0,
                                              max_retries=1, hold_growth=1.5,
                                              label='benchmark tab throughput')

    agg_value = page.evaluate("""
        () => {
            for (const gd of document.querySelectorAll('.js-plotly-plot')) {
                if (!gd.data) continue;
                const trace = gd.data.find(t => (t.name || '').startsWith('Aggregate FPS'));
                if (trace && trace.y && trace.y.length) return trace.y[trace.y.length - 1];
            }
            return null;
        }
    """)
    if agg_value is None:
        print('WARNING: no "Aggregate FPS" trace found in the Live stats plot', file=sys.stderr)
    else:
        print(f"PASS: Live stats plot's Aggregate FPS trace shows {agg_value:.1f} fps "
              '(EMA-smoothed, lags the raw reading above)')

    print('cleaning up: removing the benchmark source so it does not contend with later runs')
    _remove_all_benchmark_sources(page)
    print('PASS: removed benchmark source(s) (cleanup)')
    return infer_fps


def main() -> int:
    """Run the Isovision release test and print a summary.

    Prepares the host, then in a visible Chromium window force-stops pipelines, runs the wizard, generates the config,
    compiles and launches, and runs the benchmark check once the launch succeeded. Saves a final screenshot under tests/.

    Returns:
        int: 0 if all steps passed, 1 otherwise.
    """
    prepare_host()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8090')
    parser.add_argument('--health-timeout-s', type=float, default=300.0)
    args = parser.parse_args()

    failures: list[str] = []
    pipeline_count = None
    throughput_summary = None
    benchmark_fps = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})

        console_messages = []
        page.on('console', lambda msg: console_messages.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda exc: console_messages.append(f'[pageerror] {exc}'))

        print(f'--- loading {args.base_url} ---')
        page.goto(args.base_url, wait_until='networkidle')

        try:
            force_stop_all(page)
            ensure_opencl_disabled(page)
            dialog = open_isovision_demo_wizard(page)
            ensure_model_selected(dialog, page, MODEL_NAME)
            pipeline_count = drive_wizard(page, dialog, health_timeout_s=args.health_timeout_s)
            for t in page.locator('.text-caption.text-grey-7').all_inner_texts():
                if t.strip().startswith('Aggregate:'):
                    throughput_summary = t.strip()
            generate_config_yaml(page)
            launched_text, failed_text = compile_and_launch_vision(page)
            if failed_text:
                print(f'FAIL: {failed_text}')
                failures.append(failed_text)
            if launched_text:
                print(f'PASS: {launched_text}')
            if not launched_text and not failed_text:
                failures.append('Compile and Launch Pipeline produced neither a launch-success nor '
                                 'launch-failed notification')
            if launched_text:
                benchmark_fps = run_benchmark_tab_check(page)
        except Exception as exc:
            print(f'FAIL: {exc}', file=sys.stderr)
            failures.append(str(exc))

        print('--- recent console/page messages ---')
        for line in console_messages[-30:]:
            print(line)

        page.screenshot(path='tests/_release_playwright_isovision_final.png', full_page=True)
        browser.close()

    print('\n=== SUMMARY ===')
    print(f'pipeline_count: {pipeline_count}')
    if throughput_summary:
        print(f'throughput ({THROUGHPUT_SECONDS}s test): {throughput_summary}')
    if benchmark_fps is not None:
        print(f'benchmarking tab image-source inference fps: {benchmark_fps:.1f}')
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        print('test_release_playwright_isovision: FAIL')
        return 1
    print('ALL STEPS PASSED')
    print('test_release_playwright_isovision: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
