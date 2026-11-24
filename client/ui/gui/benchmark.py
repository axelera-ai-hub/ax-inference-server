"""Benchmarking tab backend: per-source worker processes, live stats plot, AxMonitor polling and the preview routes.

Owns the Benchmarking settings and histories (stored on core.app.state so they survive page loads), spawns and tears down benchmark_worker processes, drains their metrics into the source tiles and the Plotly chart, and serves /benchmark/thumbnail and /benchmark/stream. Widgets are created in app.py and handed in through configure().

Note:
    Environment: HOST_SERVER_URL and HOST_SERVER_API_KEY locate host_server.py (media fetch, AxMonitor stats, device power limit). Module-level setting variables mirror entries of the dicts on core.app.state; the change handlers update both.
"""

import asyncio
import concurrent.futures
import functools
import os
import queue
import shutil
import statistics
import time
from collections import deque
from datetime import datetime

import httpx
import psutil
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from nicegui import app, core, ui

from adapters import SourceAdapterError, WebcamAdapterCV
from adapters.common.rendering import decode_frame, encode_frame, resize_to_height
from benchmark_worker import MP_CONTEXT, make_adapter, run_source_worker

HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')

BENCHMARK_SOURCES: dict = core.app.state.benchmark_sources

# Default folder of the file picker.
BENCHMARK_SOURCE_DEFAULT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'test_images'))
BENCHMARK_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}
BENCHMARK_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}
# Default seconds between captures of a new source (5 fps).
BENCHMARK_PREVIEW_POLL_INTERVAL_S = 0.2
# Upper bound of the FPS input for image sources.
BENCHMARK_IMAGE_SOURCE_MAX_FPS = 2000

# 1x1 transparent GIF shown until the first thumbnail is available.
_BENCHMARK_BLANK_PIXEL = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
BENCHMARK_FRAMES_DIR = os.path.join(os.path.dirname(__file__), 'benchmark_frames')
# Frames kept on disk per source.
BENCHMARK_RING_BUFFER_FRAMES = 150
# Default cap on the pinned stream's polling rate, and the rate at which workers render frames.
BENCHMARK_STREAM_FPS = 24.0
# 0 keeps the native capture width when saving frames.
BENCHMARK_STREAM_MAX_WIDTH_PX = 0
BENCHMARK_STREAM_RESOLUTION_PRESET = '360p'
# Preset -> target height in pixels; 0 means no resize.
BENCHMARK_STREAM_RESOLUTION_HEIGHTS = {'native': 0, '720p': 720, '480p': 480, '360p': 360}
BENCHMARK_STREAM_QUALITY = 80
BENCHMARK_STREAM_FORMAT = 'webp'
# Default in-flight request cap for new sources; 0 disables it.
BENCHMARK_MAX_PENDING_INFLIGHT = 1000
# Default client-side request timeout for new sources, in seconds.
BENCHMARK_REQUEST_TIMEOUT_SEC = 65.0
BENCHMARK_AIMD_BACKOFF_ENABLED = False
if not hasattr(core.app.state, 'benchmark_stream_settings'):
    core.app.state.benchmark_stream_settings = {
        'resolution_preset': BENCHMARK_STREAM_RESOLUTION_PRESET,
        'quality': BENCHMARK_STREAM_QUALITY,
        'format': BENCHMARK_STREAM_FORMAT,
        'fps': BENCHMARK_STREAM_FPS,
        'max_width_px': BENCHMARK_STREAM_MAX_WIDTH_PX,
        'max_pending_inflight': BENCHMARK_MAX_PENDING_INFLIGHT,
        'request_timeout_sec': BENCHMARK_REQUEST_TIMEOUT_SEC,
        'aimd_backoff_enabled': BENCHMARK_AIMD_BACKOFF_ENABLED,
    }
_BENCHMARK_STREAM_SETTINGS: dict = core.app.state.benchmark_stream_settings
BENCHMARK_STREAM_PLAYBACK_DELAY_S = 2.0
_benchmark_stream_playback_delay_s = BENCHMARK_STREAM_PLAYBACK_DELAY_S
# Default seconds between thumbnail refreshes of a tile.
BENCHMARK_THUMBNAIL_REFRESH_INTERVAL_S = 7.0
_benchmark_thumbnail_refresh_interval_s = BENCHMARK_THUMBNAIL_REFRESH_INTERVAL_S
# Seconds between history samples and plot refreshes.
BENCHMARK_METRICS_SAMPLE_INTERVAL_S = 2.0
# Seconds between drains of the workers' metrics queues.
BENCHMARK_DRAIN_INTERVAL_S = 0.5
# Runs blocking worker joins and frame directory removal off the event loop.
_BENCHMARK_CLEANUP_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix='benchmark-cleanup')
BENCHMARK_METRICS_HISTORY_MAXLEN = 1000
BENCHMARK_AGGREGATE_FPS_EMA_ALPHA_DEFAULT = 0.3
BENCHMARK_AGGREGATE_FPS_HAMPEL_WINDOW_DEFAULT = 7
BENCHMARK_AGGREGATE_FPS_HAMPEL_NSIGMAS_DEFAULT = 3.0
BENCHMARK_AGGREGATE_FPS_FILTER_MODE_DEFAULT = 'ema'
# Scales the median absolute deviation to a standard deviation estimate for normal data.
_HAMPEL_MAD_SCALE_FACTOR = 1.4826


def _hampel_filter(data: list, window_size: int, n_sigmas: float) -> list:
    """Replace outliers in a series with their local median (Hampel filter).

    A point is replaced when it deviates from the median of its centered window by more than n_sigmas times the scaled median absolute deviation. The first and last window_size // 2 points are left unchanged.

    Args:
        data (list): Numeric samples.
        window_size (int): Window length in samples; an even value is rounded up to the next odd number.
        n_sigmas (float): Outlier threshold in robust standard deviations.

    Returns:
        list: A filtered copy; an unmodified copy when the series is shorter than the window.
    """

    if window_size % 2 == 0:
        window_size += 1
    n = len(data)
    k = window_size // 2
    if n <= 2 * k:
        return list(data)
    filtered = list(data)
    for i in range(k, n - k):
        window = data[i - k:i + k + 1]
        local_median = statistics.median(window)
        mad = statistics.median(abs(x - local_median) for x in window)
        threshold = n_sigmas * _HAMPEL_MAD_SCALE_FACTOR * mad
        if abs(data[i] - local_median) > threshold:
            filtered[i] = local_median
    return filtered



if not hasattr(core.app.state, 'benchmark_endpoints'):
    core.app.state.benchmark_endpoints = []
_benchmark_endpoints: list = core.app.state.benchmark_endpoints
if not hasattr(core.app.state, 'benchmark_pipeline_ids'):
    core.app.state.benchmark_pipeline_ids = []
_benchmark_pipeline_ids: list = core.app.state.benchmark_pipeline_ids
if not hasattr(core.app.state, 'benchmark_source_seq'):
    core.app.state.benchmark_source_seq = 0
if not hasattr(core.app.state, 'active_benchmark_tab'):
    core.app.state.active_benchmark_tab = 'Pipeline Editor'
# Map the legacy tab name 'Monitor' to 'Benchmarking'.
elif core.app.state.active_benchmark_tab == 'Monitor':
    core.app.state.active_benchmark_tab = 'Benchmarking'
if not hasattr(core.app.state, 'benchmark_show_flags'):
    core.app.state.benchmark_show_flags = {
        'aggregate_fps': True,
        'per_source_fps': False,
        'per_source_latency': True,
        'per_source_error': False,
        'aggregate_error': False,
        'cpu_percent': False,
        'cpu_percent_percore': False,
        'mem_percent': False,
        'monitor_aggregate_core': False,
        'monitor_aggregate_mvm': False,
        'monitor_aggregate_syscore': False,
        'monitor_aggregate_ddr': False,
        'monitor_per_device_raw': False,
        'monitor_power_sensor_0': False,
        'monitor_power_sensor_1': False,
    }
_BENCHMARK_SHOW_FLAGS: dict = core.app.state.benchmark_show_flags
_benchmark_show_aggregate_fps = _BENCHMARK_SHOW_FLAGS['aggregate_fps']
_benchmark_show_per_source_fps = _BENCHMARK_SHOW_FLAGS['per_source_fps']
_benchmark_show_per_source_latency = _BENCHMARK_SHOW_FLAGS['per_source_latency']
_benchmark_show_per_source_error = _BENCHMARK_SHOW_FLAGS['per_source_error']
_benchmark_show_aggregate_error = _BENCHMARK_SHOW_FLAGS['aggregate_error']
_benchmark_show_cpu_percent = _BENCHMARK_SHOW_FLAGS['cpu_percent']
_benchmark_show_cpu_percent_percore = _BENCHMARK_SHOW_FLAGS['cpu_percent_percore']
_benchmark_show_mem_percent = _BENCHMARK_SHOW_FLAGS['mem_percent']
_benchmark_show_monitor_aggregate_core = _BENCHMARK_SHOW_FLAGS['monitor_aggregate_core']
_benchmark_show_monitor_aggregate_mvm = _BENCHMARK_SHOW_FLAGS['monitor_aggregate_mvm']
_benchmark_show_monitor_aggregate_syscore = _BENCHMARK_SHOW_FLAGS['monitor_aggregate_syscore']
_benchmark_show_monitor_aggregate_ddr = _BENCHMARK_SHOW_FLAGS['monitor_aggregate_ddr']
_benchmark_show_monitor_per_device_raw = _BENCHMARK_SHOW_FLAGS['monitor_per_device_raw']
_benchmark_show_monitor_power_sensor_0 = _BENCHMARK_SHOW_FLAGS.setdefault('monitor_power_sensor_0', False)
_benchmark_show_monitor_power_sensor_1 = _BENCHMARK_SHOW_FLAGS.setdefault('monitor_power_sensor_1', False)
if not hasattr(core.app.state, 'benchmark_misc_settings'):
    core.app.state.benchmark_misc_settings = {
        'metrics_history_maxlen': BENCHMARK_METRICS_HISTORY_MAXLEN,
        'thumbnail_refresh_interval_s': BENCHMARK_THUMBNAIL_REFRESH_INTERVAL_S,
        'stream_playback_delay_s': BENCHMARK_STREAM_PLAYBACK_DELAY_S,
        'aggregate_fps_ema_alpha': BENCHMARK_AGGREGATE_FPS_EMA_ALPHA_DEFAULT,
        'aggregate_fps_filter_mode': BENCHMARK_AGGREGATE_FPS_FILTER_MODE_DEFAULT,
        'aggregate_fps_hampel_window': BENCHMARK_AGGREGATE_FPS_HAMPEL_WINDOW_DEFAULT,
        'aggregate_fps_hampel_nsigmas': BENCHMARK_AGGREGATE_FPS_HAMPEL_NSIGMAS_DEFAULT,
    }
_BENCHMARK_MISC_SETTINGS: dict = core.app.state.benchmark_misc_settings
_benchmark_metrics_history_maxlen = _BENCHMARK_MISC_SETTINGS['metrics_history_maxlen']
_benchmark_aggregate_fps_ema_alpha = _BENCHMARK_MISC_SETTINGS['aggregate_fps_ema_alpha']
_benchmark_aggregate_fps_filter_mode = _BENCHMARK_MISC_SETTINGS['aggregate_fps_filter_mode']
_benchmark_aggregate_fps_hampel_window = _BENCHMARK_MISC_SETTINGS['aggregate_fps_hampel_window']
_benchmark_aggregate_fps_hampel_nsigmas = _BENCHMARK_MISC_SETTINGS['aggregate_fps_hampel_nsigmas']
_benchmark_thumbnail_refresh_interval_s = _BENCHMARK_MISC_SETTINGS['thumbnail_refresh_interval_s']
_benchmark_stream_playback_delay_s = _BENCHMARK_MISC_SETTINGS['stream_playback_delay_s']
if not hasattr(core.app.state, 'benchmark_system_metrics_history'):
    core.app.state.benchmark_system_metrics_history = deque(maxlen=BENCHMARK_METRICS_HISTORY_MAXLEN)
BENCHMARK_SYSTEM_METRICS_HISTORY: deque = core.app.state.benchmark_system_metrics_history
if not hasattr(core.app.state, 'benchmark_aggregate_history'):
    core.app.state.benchmark_aggregate_history = deque(maxlen=BENCHMARK_METRICS_HISTORY_MAXLEN)
BENCHMARK_AGGREGATE_HISTORY: deque = core.app.state.benchmark_aggregate_history
# Prime psutil's counters so the first sample in the metrics tick is meaningful.
psutil.cpu_percent(interval=None)
psutil.cpu_percent(interval=None, percpu=True)
_BENCHMARK_CPU_COUNT = psutil.cpu_count(logical=True) or 1

_BENCHMARK_MEDIA_STAGE_LABELS = {
    'downloading': 'Downloading',
    'preprocessing': 'Preprocessing',
    'transferring': 'Transferring',
}


async def _start_benchmark_media_fetch() -> dict:
    """Ask host_server.py to start fetching the standard test media.

    Returns:
        dict: {'reachable': False} when HOST_SERVER_URL is unset, {'reachable': False, 'error': ...} on a request failure, {'reachable': True} when the fetch started or was already running (HTTP 200 or 409), else {'reachable': True, 'error': detail}.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/benchmark-media/fetch',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
        if resp.status_code in (200, 409):
            return {'reachable': True}
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


async def _poll_benchmark_media_status() -> dict:
    """Read the progress of the test media fetch from host_server.py.

    Returns:
        dict: The server's status JSON plus 'reachable': True, or the same reachable/error shapes as _start_benchmark_media_fetch.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/benchmark-media/status',
                headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
        if resp.status_code == 200:
            result = resp.json()
            result['reachable'] = True
            return result
        try:
            detail = resp.json().get('detail', resp.text)
        except ValueError:
            detail = resp.text
        return {'reachable': True, 'error': detail}
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}



benchmark_aggregate_fps_ema_alpha_input = None
benchmark_aggregate_fps_hampel_nsigmas_input = None
benchmark_aggregate_fps_hampel_window_input = None
benchmark_no_sources_label = None
benchmark_source_count_label = None
benchmark_stats_plot = None
sources_container = None


def configure(
    *, benchmark_aggregate_fps_ema_alpha_input_, benchmark_aggregate_fps_hampel_nsigmas_input_,
    benchmark_aggregate_fps_hampel_window_input_, benchmark_no_sources_label_,
    benchmark_source_count_label_, benchmark_stats_plot_, sources_container_,
) -> None:
    """Receive the widgets built in app.py.

    Args:
        benchmark_aggregate_fps_ema_alpha_input_: EMA alpha number input.
        benchmark_aggregate_fps_hampel_nsigmas_input_: Hampel n-sigmas number input.
        benchmark_aggregate_fps_hampel_window_input_: Hampel window number input.
        benchmark_no_sources_label_: Placeholder label shown while no source has history.
        benchmark_source_count_label_: Label showing the number of sources.
        benchmark_stats_plot_: The Plotly element of the live stats chart.
        sources_container_: Column that holds the source tiles.
    """
    global benchmark_aggregate_fps_ema_alpha_input, benchmark_aggregate_fps_hampel_nsigmas_input
    global benchmark_aggregate_fps_hampel_window_input, benchmark_no_sources_label
    global benchmark_source_count_label, benchmark_stats_plot, sources_container
    benchmark_aggregate_fps_ema_alpha_input = benchmark_aggregate_fps_ema_alpha_input_
    benchmark_aggregate_fps_hampel_nsigmas_input = benchmark_aggregate_fps_hampel_nsigmas_input_
    benchmark_aggregate_fps_hampel_window_input = benchmark_aggregate_fps_hampel_window_input_
    benchmark_no_sources_label = benchmark_no_sources_label_
    benchmark_source_count_label = benchmark_source_count_label_
    benchmark_stats_plot = benchmark_stats_plot_
    sources_container = sources_container_

def _benchmark_list_dir(path: str) -> list:
    """List a directory for the file picker.

    Shows a toast and returns an empty list when it cannot be read.

    Args:
        path (str): Directory to list.

    Returns:
        list: (name, is_dir) tuples without hidden entries, directories first, then sorted case-insensitively.
    """
    try:
        with os.scandir(path) as it:
            entries = [(e.name, e.is_dir(follow_symlinks=False)) for e in it if not e.name.startswith('.')]
    except OSError as exc:
        ui.notify(f'cannot list {path}: {exc}', type='negative')
        return []
    entries.sort(key=lambda t: (not t[1], t[0].lower()))
    return entries


def _update_benchmark_source_count() -> None:
    """Show the current number of sources in the count label."""
    benchmark_source_count_label.set_text(str(len(BENCHMARK_SOURCES)))


def _benchmark_remove_source(source_id: str) -> None:
    """Remove a source: stop its worker, delete its frames and remove its widgets.

    The widgets go immediately. The worker is joined (3 s), terminated if still alive (2 s more), and its frame directory removed, in a background task on the cleanup executor. Unknown ids are ignored.

    Args:
        source_id (str): Id of the source in BENCHMARK_SOURCES.
    """
    entry = BENCHMARK_SOURCES.pop(source_id, None)
    if entry is None:
        return
    _update_benchmark_source_count()
    entry['stop_event'].set()
    process = entry['process']
    frame_dir = entry.get('frame_dir')

    async def _cleanup_process() -> None:
        """Join or terminate the worker process and delete its frame directory without blocking the event loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_BENCHMARK_CLEANUP_EXECUTOR, process.join, 3.0)
        if process.is_alive():
            process.terminate()
            await loop.run_in_executor(_BENCHMARK_CLEANUP_EXECUTOR, process.join, 2.0)
        if frame_dir:
            await loop.run_in_executor(
                _BENCHMARK_CLEANUP_EXECUTOR,
                functools.partial(shutil.rmtree, frame_dir, ignore_errors=True))

    asyncio.create_task(_cleanup_process())
    if entry.get('pinned_dialog') is not None:
        entry['pinned_dialog'].delete()
    entry['card'].delete()


def _on_benchmark_remove_all_clicked() -> None:
    """Remove every source and report how many were removed."""
    source_ids = list(BENCHMARK_SOURCES.keys())
    if not source_ids:
        ui.notify('no sources to remove', type='info')
        return
    for source_id in source_ids:
        _benchmark_remove_source(source_id)
    ui.notify(f'removed {len(source_ids)} source(s)', type='positive')


def _on_benchmark_endpoints_changed(value) -> None:
    """Store the inference endpoint list from the comma-separated input.

    Only sources added afterwards use it.

    Args:
        value: Input text such as 'host:port, host2:port2'; None or empty clears the list.
    """

    global _benchmark_endpoints
    _benchmark_endpoints = [e.strip() for e in (value or '').split(',') if e.strip()]
    core.app.state.benchmark_endpoints = _benchmark_endpoints


def _on_benchmark_pipeline_ids_changed(value) -> None:
    """Store the pipeline id list used for backpressure monitoring from the comma-separated input.

    Only sources added afterwards use it.

    Args:
        value: Input text of comma-separated pipeline ids; None or empty clears the list.
    """
    global _benchmark_pipeline_ids
    _benchmark_pipeline_ids = [p.strip() for p in (value or '').split(',') if p.strip()]
    core.app.state.benchmark_pipeline_ids = _benchmark_pipeline_ids


def _on_benchmark_show_aggregate_fps_changed(value: bool) -> None:
    """Show or hide the Aggregate FPS series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_aggregate_fps
    _benchmark_show_aggregate_fps = bool(value)
    _BENCHMARK_SHOW_FLAGS['aggregate_fps'] = _benchmark_show_aggregate_fps
    _refresh_benchmark_plots()


def _on_benchmark_show_per_source_fps_changed(value: bool) -> None:
    """Show or hide the per-source FPS series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_per_source_fps
    _benchmark_show_per_source_fps = bool(value)
    _BENCHMARK_SHOW_FLAGS['per_source_fps'] = _benchmark_show_per_source_fps
    _refresh_benchmark_plots()


def _on_benchmark_show_per_source_latency_changed(value: bool) -> None:
    """Show or hide the per-source latency series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_per_source_latency
    _benchmark_show_per_source_latency = bool(value)
    _BENCHMARK_SHOW_FLAGS['per_source_latency'] = _benchmark_show_per_source_latency
    _refresh_benchmark_plots()


def _on_benchmark_show_per_source_error_changed(value: bool) -> None:
    """Show or hide the per-source error series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_per_source_error
    _benchmark_show_per_source_error = bool(value)
    _BENCHMARK_SHOW_FLAGS['per_source_error'] = _benchmark_show_per_source_error
    _refresh_benchmark_plots()


def _on_benchmark_show_aggregate_error_changed(value: bool) -> None:
    """Show or hide the aggregate error series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_aggregate_error
    _benchmark_show_aggregate_error = bool(value)
    _BENCHMARK_SHOW_FLAGS['aggregate_error'] = _benchmark_show_aggregate_error
    _refresh_benchmark_plots()


def _on_benchmark_show_cpu_percent_changed(value: bool) -> None:
    """Show or hide the host CPU utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_cpu_percent
    _benchmark_show_cpu_percent = bool(value)
    _BENCHMARK_SHOW_FLAGS['cpu_percent'] = _benchmark_show_cpu_percent
    _refresh_benchmark_plots()


def _on_benchmark_show_cpu_percent_percore_changed(value: bool) -> None:
    """Show or hide the per-core CPU utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_cpu_percent_percore
    _benchmark_show_cpu_percent_percore = bool(value)
    _BENCHMARK_SHOW_FLAGS['cpu_percent_percore'] = _benchmark_show_cpu_percent_percore
    _refresh_benchmark_plots()


def _on_benchmark_show_mem_percent_changed(value: bool) -> None:
    """Show or hide the host memory utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_mem_percent
    _benchmark_show_mem_percent = bool(value)
    _BENCHMARK_SHOW_FLAGS['mem_percent'] = _benchmark_show_mem_percent
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_aggregate_core_changed(value: bool) -> None:
    """Show or hide the AxMonitor aggregate core utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_aggregate_core
    _benchmark_show_monitor_aggregate_core = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_aggregate_core'] = _benchmark_show_monitor_aggregate_core
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_aggregate_mvm_changed(value: bool) -> None:
    """Show or hide the AxMonitor aggregate MVM utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_aggregate_mvm
    _benchmark_show_monitor_aggregate_mvm = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_aggregate_mvm'] = _benchmark_show_monitor_aggregate_mvm
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_aggregate_syscore_changed(value: bool) -> None:
    """Show or hide the AxMonitor aggregate sys-core utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_aggregate_syscore
    _benchmark_show_monitor_aggregate_syscore = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_aggregate_syscore'] = _benchmark_show_monitor_aggregate_syscore
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_aggregate_ddr_changed(value: bool) -> None:
    """Show or hide the AxMonitor aggregate DDR utilization series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_aggregate_ddr
    _benchmark_show_monitor_aggregate_ddr = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_aggregate_ddr'] = _benchmark_show_monitor_aggregate_ddr
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_per_device_raw_changed(value: bool) -> None:
    """Show or hide the AxMonitor raw per-device series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_per_device_raw
    _benchmark_show_monitor_per_device_raw = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_per_device_raw'] = _benchmark_show_monitor_per_device_raw
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_power_sensor_0_changed(value: bool) -> None:
    """Show or hide the AxMonitor power sensor 0 series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_power_sensor_0
    _benchmark_show_monitor_power_sensor_0 = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_power_sensor_0'] = _benchmark_show_monitor_power_sensor_0
    _refresh_benchmark_plots()


def _on_benchmark_show_monitor_power_sensor_1_changed(value: bool) -> None:
    """Show or hide the AxMonitor power sensor 1 series on the live stats plot, then redraw it.

    Args:
        value (bool): True to show the series.
    """
    global _benchmark_show_monitor_power_sensor_1
    _benchmark_show_monitor_power_sensor_1 = bool(value)
    _BENCHMARK_SHOW_FLAGS['monitor_power_sensor_1'] = _benchmark_show_monitor_power_sensor_1
    _refresh_benchmark_plots()


def _on_benchmark_history_maxlen_changed(value) -> None:
    """Resize the per-source and host-metrics history buffers.

    Ignores non-integer or non-positive values. Existing per-source histories and the host system history are rebuilt keeping their newest samples. BENCHMARK_AGGREGATE_HISTORY and MONITOR_STATS_HISTORY are not resized.

    Args:
        value: New maximum number of samples per buffer.
    """
    global _benchmark_metrics_history_maxlen
    try:
        maxlen = int(value)
    except (TypeError, ValueError):
        return
    if maxlen <= 0:
        return
    _benchmark_metrics_history_maxlen = maxlen
    _BENCHMARK_MISC_SETTINGS['metrics_history_maxlen'] = maxlen
    for entry in BENCHMARK_SOURCES.values():
        entry['metrics_history'] = deque(entry['metrics_history'], maxlen=maxlen)
    global BENCHMARK_SYSTEM_METRICS_HISTORY
    BENCHMARK_SYSTEM_METRICS_HISTORY = deque(BENCHMARK_SYSTEM_METRICS_HISTORY, maxlen=maxlen)
    core.app.state.benchmark_system_metrics_history = BENCHMARK_SYSTEM_METRICS_HISTORY
    _refresh_benchmark_plots()


def _on_benchmark_aggregate_fps_ema_alpha_changed(value) -> None:
    """Set the EMA smoothing factor of the Aggregate FPS line and redraw.

    Args:
        value: Alpha in (0, 1]; other values are ignored.
    """
    global _benchmark_aggregate_fps_ema_alpha
    try:
        alpha = float(value)
    except (TypeError, ValueError):
        return
    if not (0.0 < alpha <= 1.0):
        return
    _benchmark_aggregate_fps_ema_alpha = alpha
    _BENCHMARK_MISC_SETTINGS['aggregate_fps_ema_alpha'] = alpha
    _refresh_benchmark_plots()


def _on_benchmark_aggregate_fps_filter_mode_changed(value) -> None:
    """Select the Aggregate FPS filter and show the matching parameter inputs.

    Args:
        value (str): 'ema' or 'hampel'; anything else is ignored.
    """
    global _benchmark_aggregate_fps_filter_mode
    if value not in ('ema', 'hampel'):
        return
    _benchmark_aggregate_fps_filter_mode = value
    _BENCHMARK_MISC_SETTINGS['aggregate_fps_filter_mode'] = value
    benchmark_aggregate_fps_ema_alpha_input.set_visibility(value == 'ema')
    benchmark_aggregate_fps_hampel_window_input.set_visibility(value == 'hampel')
    benchmark_aggregate_fps_hampel_nsigmas_input.set_visibility(value == 'hampel')
    _refresh_benchmark_plots()


def _on_benchmark_hampel_window_changed(value) -> None:
    """Set the Hampel filter window size and redraw.

    Args:
        value: Window length in samples; values below 3 are ignored.
    """
    global _benchmark_aggregate_fps_hampel_window
    try:
        window = int(value)
    except (TypeError, ValueError):
        return
    if window < 3:
        return
    _benchmark_aggregate_fps_hampel_window = window
    _BENCHMARK_MISC_SETTINGS['aggregate_fps_hampel_window'] = window
    _refresh_benchmark_plots()


def _on_benchmark_hampel_nsigmas_changed(value) -> None:
    """Set the Hampel filter threshold and redraw.

    Args:
        value: Threshold in robust standard deviations; values <= 0 are ignored.
    """
    global _benchmark_aggregate_fps_hampel_nsigmas
    try:
        nsigmas = float(value)
    except (TypeError, ValueError):
        return
    if nsigmas <= 0:
        return
    _benchmark_aggregate_fps_hampel_nsigmas = nsigmas
    _BENCHMARK_MISC_SETTINGS['aggregate_fps_hampel_nsigmas'] = nsigmas
    _refresh_benchmark_plots()


def _on_benchmark_thumbnail_interval_changed(value) -> None:
    """Set how often source tile thumbnails are refreshed.

    Args:
        value: Seconds; values <= 0 are ignored.
    """
    global _benchmark_thumbnail_refresh_interval_s
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return
    if seconds <= 0:
        return
    _benchmark_thumbnail_refresh_interval_s = seconds
    _BENCHMARK_MISC_SETTINGS['thumbnail_refresh_interval_s'] = seconds


def _on_benchmark_stream_fps_changed(value) -> None:
    """Set the frame-rate cap of the pinned MJPEG stream.

    Read by running streams on their next loop pass.

    Args:
        value: Frames per second; values <= 0 are ignored.
    """
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return
    if fps <= 0:
        return
    _BENCHMARK_STREAM_SETTINGS['fps'] = fps


def _on_benchmark_stream_max_width_changed(value) -> None:
    """Set the maximum width of frames saved to the ring buffer.

    Applies to sources added afterwards.

    Args:
        value: Width in pixels, 0 keeps the native size; negative values are ignored.
    """
    try:
        width = int(value)
    except (TypeError, ValueError):
        return
    if width < 0:
        return
    _BENCHMARK_STREAM_SETTINGS['max_width_px'] = width


def _on_benchmark_backpressure_changed(value) -> None:
    """Set the in-flight request cap given to new sources.

    Args:
        value: Maximum in-flight requests, 0 disables the cap; negative values are ignored.
    """
    try:
        cap = int(value)
    except (TypeError, ValueError):
        return
    if cap < 0:
        return
    _BENCHMARK_STREAM_SETTINGS['max_pending_inflight'] = cap


def _on_benchmark_request_timeout_changed(value) -> None:
    """Set the client-side request timeout given to new sources.

    Args:
        value: Seconds; values <= 0 are ignored.
    """
    try:
        secs = float(value)
    except (TypeError, ValueError):
        return
    if secs <= 0:
        return
    _BENCHMARK_STREAM_SETTINGS['request_timeout_sec'] = secs


def _on_benchmark_aimd_backoff_changed(value) -> None:
    """Enable or disable AIMD backoff for new sources.

    Args:
        value (bool): True to enable.
    """
    _BENCHMARK_STREAM_SETTINGS['aimd_backoff_enabled'] = bool(value)


def _on_source_target_fps_changed(source_id: str, value) -> None:
    """Retarget the capture rate of a running source.

    Writes 1/fps into the worker's shared poll interval value. Ignores unknown sources and values that are not positive numbers.

    Args:
        source_id (str): Id of the source.
        value: Target frames per second.
    """
    entry = BENCHMARK_SOURCES.get(source_id)
    if entry is None:
        return
    poll_interval_value = entry.get('poll_interval_value')
    if poll_interval_value is None:
        return
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return
    if fps <= 0:
        return
    poll_interval_value.value = 1.0 / fps


def _on_benchmark_stream_resolution_changed(value) -> None:
    """Select the resolution preset of the pinned stream.

    Args:
        value (str): A key of BENCHMARK_STREAM_RESOLUTION_HEIGHTS; others are ignored.
    """
    if value not in BENCHMARK_STREAM_RESOLUTION_HEIGHTS:
        return
    _BENCHMARK_STREAM_SETTINGS['resolution_preset'] = value


def _on_benchmark_stream_quality_changed(value) -> None:
    """Set the encode quality of the pinned stream.

    Args:
        value: Integer from 1 to 100; others are ignored.
    """
    try:
        quality = int(value)
    except (TypeError, ValueError):
        return
    if not (1 <= quality <= 100):
        return
    _BENCHMARK_STREAM_SETTINGS['quality'] = quality


def _on_benchmark_stream_format_changed(value) -> None:
    """Select the wire format of the pinned stream.

    Args:
        value (str): 'jpeg' or 'webp'; anything else is ignored.
    """
    if value not in ('jpeg', 'webp'):
        return
    _BENCHMARK_STREAM_SETTINGS['format'] = value


def _on_benchmark_playback_delay_changed(value) -> None:
    """Set the pinned-stream playback delay and push it to the browser.

    Args:
        value: Delay in seconds; negative values are ignored.
    """
    global _benchmark_stream_playback_delay_s
    try:
        delay_s = float(value)
    except (TypeError, ValueError):
        return
    if delay_s < 0:
        return
    _benchmark_stream_playback_delay_s = delay_s
    _BENCHMARK_MISC_SETTINGS['stream_playback_delay_s'] = delay_s
    ui.run_javascript(f'window.__pinnedStreamPlaybackDelayMs = {delay_s * 1000.0};')


def _drain_one_metrics_queue(mq) -> dict | None:
    """Empty a worker's metrics queue without blocking.

    Args:
        mq (multiprocessing.Queue): The worker's metrics queue.

    Returns:
        dict | None: The newest snapshot, or None when the queue was empty.
    """

    metrics = None
    try:
        while True:
            metrics = mq.get_nowait()
    except queue.Empty:
        pass
    return metrics


async def _drain_source_metrics(source_id: str, entry: dict, now: float) -> None:
    """Read a source's newest metrics snapshot and update its tile.

    Clears the entry's in-flight flag when done. The snapshot is dropped if the source was removed meanwhile; a RuntimeError from widgets that no longer exist is ignored.

    Args:
        source_id (str): Id of the source.
        entry (dict): The source's BENCHMARK_SOURCES entry.
        now (float): time.monotonic() timestamp of the drain tick.
    """
    try:
        metrics = await asyncio.to_thread(_drain_one_metrics_queue, entry['metrics_queue'])
    finally:
        entry['_drain_in_flight'] = False
    if metrics is None or BENCHMARK_SOURCES.get(source_id) is not entry:
        return
    entry['latest_metrics'] = metrics
    try:
        _update_source_widgets(entry, metrics, source_id, now)
    except RuntimeError:
        pass


def _update_source_widgets(entry: dict, metrics: dict, source_id: str, now: float) -> None:
    """Apply a metrics snapshot to a source tile.

    Updates the status, capture/inference text, status icon (red: backpressure active, orange: inference errors seen, green: clean), in-flight bar (orange from 70 % of the cap, red at the cap) and backoff badge, and re-points the thumbnail when the refresh interval has elapsed.

    Args:
        entry (dict): The source's BENCHMARK_SOURCES entry.
        metrics (dict): Snapshot published by benchmark_worker.
        source_id (str): Id of the source.
        now (float): time.monotonic() timestamp of the drain tick.
    """
    entry['status_label'].set_text(metrics.get('status', 'live'))
    entry['fps_label'].set_text(f"{metrics.get('capture_fps', 0.0):.1f} fps (capture)")
    if 'infer_fps' in metrics:
        lat = metrics.get('latency_ms')
        lat_str = f'{lat:.0f}ms' if lat is not None else '--'
        drop_reason = metrics.get('drop_reason') or ''
        infer_text = (
            f"infer: {metrics['infer_fps']:.1f} fps, {lat_str}, "
            f"{metrics.get('det_count', 0)} det, {metrics.get('infer_errors', 0)} err"
            + (f' ({drop_reason})' if drop_reason else '')
        )
        entry['infer_label'].set_text(infer_text)
        entry['infer_tooltip'].text = infer_text
        if metrics.get('backpressure_active'):
            entry['status_icon'].set_name('cancel').set_text_color('red')
        elif metrics.get('infer_errors', 0) > 0:
            entry['status_icon'].set_name('help').set_text_color('orange')
        else:
            entry['status_icon'].set_name('check_circle').set_text_color('green')
        inflight_cap = metrics.get('inflight_cap') or 0
        if inflight_cap > 0:
            ratio = min(1.0, metrics.get('inflight', 0) / inflight_cap)
            entry['inflight_bar'].set_value(ratio)
            entry['inflight_bar'].props(
                f"color={'red' if ratio >= 1.0 else 'orange' if ratio >= 0.7 else 'green'}")
            entry['inflight_bar'].set_visibility(True)
        else:
            entry['inflight_bar'].set_visibility(False)
        backoff_multiplier = metrics.get('backoff_multiplier', 1.0)
        if backoff_multiplier > 1.0:
            entry['backoff_label'].set_text(f'÷{backoff_multiplier:.2g}')
            entry['backoff_label'].set_visibility(True)
        else:
            entry['backoff_label'].set_visibility(False)
    if metrics.get('has_frame') and now - entry['last_thumbnail_refresh_ts'] >= _benchmark_thumbnail_refresh_interval_s:
        entry['last_thumbnail_refresh_ts'] = now
        entry['img'].set_source(f'/benchmark/thumbnail/{source_id}?v={now}')


def _benchmark_drain_tick() -> None:
    """Timer callback that starts one metrics drain task per source, skipping sources whose previous drain is still running."""

    now = time.monotonic()
    for source_id, entry in BENCHMARK_SOURCES.items():
        if entry.get('_drain_in_flight'):
            continue
        entry['_drain_in_flight'] = True
        asyncio.create_task(_drain_source_metrics(source_id, entry, now))


def _benchmark_metrics_tick() -> None:
    """Timer callback that records one history sample and redraws the plot.

    Appends the latest inference metrics of each source to its history, the summed FPS and errors to the aggregate history, and host CPU, memory and per-core CPU to the system history.
    """
    now = time.time()
    agg_fps = 0.0
    agg_errors = 0
    have_sample = False
    for entry in BENCHMARK_SOURCES.values():
        metrics = entry.get('latest_metrics')
        if metrics is None or 'infer_fps' not in metrics:
            continue
        entry['metrics_history'].append(
            (now, metrics['infer_fps'], metrics.get('latency_ms'), metrics.get('infer_errors', 0))
        )
        agg_fps += metrics['infer_fps']
        agg_errors += metrics.get('infer_errors', 0)
        have_sample = True
    if have_sample:
        BENCHMARK_AGGREGATE_HISTORY.append((now, agg_fps, agg_errors))
    percore = psutil.cpu_percent(interval=None, percpu=True)
    BENCHMARK_SYSTEM_METRICS_HISTORY.append(
        (now, psutil.cpu_percent(interval=None), psutil.virtual_memory().percent, percore)
    )
    _refresh_benchmark_plots()


def _benchmark_combined_plot_layout() -> dict:
    """Build the Plotly layout of the live stats chart for the current series selection.

    Left axis: fps and/or errors. Right axes: latency (ms), percent (CPU, memory and AxMonitor utilization) and watts; the percent and watt axes are visible only while one of their series is enabled.

    Returns:
        dict: Plotly layout.
    """

    left_parts = []
    if _benchmark_show_aggregate_fps or _benchmark_show_per_source_fps:
        left_parts.append('fps')
    if _benchmark_show_aggregate_error or _benchmark_show_per_source_error:
        left_parts.append('errors')
    left_title = ' / '.join(left_parts) if left_parts else '(enable a series →)'
    right_title = 'latency (ms)' if _benchmark_show_per_source_latency else ''
    pct_active = (
        _benchmark_show_cpu_percent or _benchmark_show_mem_percent or _benchmark_show_cpu_percent_percore
        or _benchmark_show_monitor_aggregate_core or _benchmark_show_monitor_aggregate_mvm
        or _benchmark_show_monitor_aggregate_syscore or _benchmark_show_monitor_aggregate_ddr
        or _benchmark_show_monitor_per_device_raw
    )
    return {
        'title': {'text': 'FPS / latency / errors (toggle series in Advanced Settings)', 'font': {'size': 13}},
        'margin': {'l': 65, 'r': 65, 't': 30, 'b': 30},
        'height': 420,
        'xaxis': {'type': 'date'},
        'yaxis': {'title': {'text': left_title}, 'rangemode': 'tozero'},
        'yaxis2': {'title': {'text': right_title}, 'rangemode': 'tozero', 'overlaying': 'y', 'side': 'right'},
        'yaxis3': {
            'title': {'text': '%'}, 'range': [-3, 100], 'overlaying': 'y', 'side': 'right',
            'anchor': 'free', 'autoshift': True, 'visible': pct_active,
        },
        'yaxis4': {
            'title': {'text': 'W'}, 'rangemode': 'tozero', 'overlaying': 'y', 'side': 'right',
            'anchor': 'free', 'autoshift': True,
            'visible': _benchmark_show_monitor_power_sensor_0 or _benchmark_show_monitor_power_sensor_1,
        },
        'legend': {'orientation': 'h'},
        'uirevision': 'benchmark-live-stats',
    }


def _refresh_benchmark_plots() -> None:
    """Rebuild every enabled trace from the histories and update the live stats chart.

    Covers per-source series, the Aggregate FPS line (EMA or Hampel filtered) and aggregate errors, host CPU and memory, and the AxMonitor series. Host series are cut to the length of the longest source history while sources exist. Shows the placeholder label when no source has history.
    """
    active = [(sid, e) for sid, e in BENCHMARK_SOURCES.items() if e.get('metrics_history')]
    traces = []
    for _sid, entry in active:
        hist = list(entry['metrics_history'])
        if not hist:
            continue
        x = [datetime.fromtimestamp(t).isoformat() for t, _, _, _ in hist]
        if _benchmark_show_per_source_fps:
            traces.append({'type': 'scatter', 'mode': 'lines', 'name': f"{entry['name']} (fps)",
                            'yaxis': 'y', 'x': x, 'y': [fps for _, fps, _, _ in hist]})
        if _benchmark_show_per_source_latency:
            traces.append({'type': 'scatter', 'mode': 'lines', 'name': f"{entry['name']} (latency)",
                            'yaxis': 'y2', 'x': x, 'y': [lat for _, _, lat, _ in hist]})
        if _benchmark_show_per_source_error:
            traces.append({'type': 'scatter', 'mode': 'lines', 'name': f"{entry['name']} (errors)",
                            'yaxis': 'y', 'x': x, 'y': [err for _, _, _, err in hist]})
    if (_benchmark_show_aggregate_fps or _benchmark_show_aggregate_error) and BENCHMARK_AGGREGATE_HISTORY:
        agg_hist = list(BENCHMARK_AGGREGATE_HISTORY)
        agg_x = [datetime.fromtimestamp(t).isoformat() for t, _, _ in agg_hist]
        if _benchmark_show_aggregate_fps:
            raw_vals = [fps for _, fps, _ in agg_hist]
            if _benchmark_aggregate_fps_filter_mode == 'hampel':
                filtered_vals = _hampel_filter(
                    raw_vals, _benchmark_aggregate_fps_hampel_window, _benchmark_aggregate_fps_hampel_nsigmas)
                trace_name = 'Aggregate FPS (Hampel)'
            else:
                alpha = _benchmark_aggregate_fps_ema_alpha
                filtered_vals = []
                prev = None
                for v in raw_vals:
                    prev = v if prev is None else alpha * v + (1.0 - alpha) * prev
                    filtered_vals.append(prev)
                trace_name = 'Aggregate FPS (EMA)'
            traces.append({
                'type': 'scatter', 'mode': 'lines', 'name': trace_name, 'yaxis': 'y',
                'line': {'width': 3, 'dash': 'dot'},
                'x': agg_x, 'y': filtered_vals,
            })
        if _benchmark_show_aggregate_error:
            traces.append({
                'type': 'scatter', 'mode': 'lines', 'name': 'Aggregate errors', 'yaxis': 'y',
                'line': {'width': 3, 'dash': 'dash'},
                'x': agg_x, 'y': [err for _, _, err in agg_hist],
            })
    pct_series_wanted = (_benchmark_show_cpu_percent or _benchmark_show_mem_percent
                         or _benchmark_show_cpu_percent_percore)
    if pct_series_wanted and BENCHMARK_SYSTEM_METRICS_HISTORY:
        sys_hist = list(BENCHMARK_SYSTEM_METRICS_HISTORY)
        if active:
            target_len = max(len(e['metrics_history']) for _, e in active)
            sys_hist = sys_hist[-target_len:]
        sys_x = [datetime.fromtimestamp(t).isoformat() for t, _, _, _ in sys_hist]
        if _benchmark_show_cpu_percent:
            traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'CPU %', 'yaxis': 'y3',
                            'x': sys_x, 'y': [cpu for _, cpu, _, _ in sys_hist]})
        if _benchmark_show_mem_percent:
            traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'Memory %', 'yaxis': 'y3',
                            'x': sys_x, 'y': [mem for _, _, mem, _ in sys_hist]})
        if _benchmark_show_cpu_percent_percore:
            for i in range(_BENCHMARK_CPU_COUNT):
                traces.append({
                    'type': 'scatter', 'mode': 'lines', 'name': f'CPU core {i} %', 'yaxis': 'y3',
                    'x': sys_x,
                    'y': [percore[i] if i < len(percore) else None for _, _, _, percore in sys_hist],
                })
    monitor_series_wanted = (
        _benchmark_show_monitor_aggregate_core or _benchmark_show_monitor_aggregate_mvm
        or _benchmark_show_monitor_aggregate_syscore or _benchmark_show_monitor_aggregate_ddr
        or _benchmark_show_monitor_per_device_raw
        or _benchmark_show_monitor_power_sensor_0 or _benchmark_show_monitor_power_sensor_1
    )
    if monitor_series_wanted and MONITOR_STATS_HISTORY:
        mon_hist = list(MONITOR_STATS_HISTORY)
        mon_x = [datetime.fromtimestamp(t).isoformat() for t, _ in mon_hist]
        if (_benchmark_show_monitor_aggregate_core or _benchmark_show_monitor_aggregate_mvm
                or _benchmark_show_monitor_aggregate_syscore or _benchmark_show_monitor_aggregate_ddr):
            agg_series = [_compute_monitor_aggregates(devices) for _, devices in mon_hist]
            if _benchmark_show_monitor_aggregate_core:
                traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'Aggregate core %', 'yaxis': 'y3',
                                'x': mon_x, 'y': [a['core_pct'] for a in agg_series]})
            if _benchmark_show_monitor_aggregate_mvm:
                traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'Aggregate MVM %', 'yaxis': 'y3',
                                'x': mon_x, 'y': [a['mvm_pct'] for a in agg_series]})
            if _benchmark_show_monitor_aggregate_syscore:
                traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'Aggregate sys-core %', 'yaxis': 'y3',
                                'x': mon_x, 'y': [a['syscore_pct'] for a in agg_series]})
            if _benchmark_show_monitor_aggregate_ddr:
                traces.append({'type': 'scatter', 'mode': 'lines', 'name': 'Aggregate DDR %', 'yaxis': 'y3',
                                'x': mon_x, 'y': [a['ddr_pct'] for a in agg_series]})
        for sensor, wanted in ((0, _benchmark_show_monitor_power_sensor_0),
                               (1, _benchmark_show_monitor_power_sensor_1)):
            if not wanted:
                continue
            power_y = []
            for _, devices in mon_hist:
                vals = [d.get(f'power_sensor_{sensor}_w') for d in devices.values()]
                vals = [v for v in vals if v is not None]
                power_y.append(sum(vals) if vals else None)
            if any(v is not None for v in power_y):
                traces.append({'type': 'scatter', 'mode': 'lines', 'name': f'All devices power sensor {sensor} (W)',
                                'yaxis': 'y4', 'x': mon_x, 'y': power_y})
        if _benchmark_show_monitor_per_device_raw:
            device_indices = sorted({idx for _, devices in mon_hist for idx in devices.keys()})
            for idx in device_indices:
                ddr_y = [devices.get(idx, {}).get('ddr_pct') for _, devices in mon_hist]
                if any(v is not None for v in ddr_y):
                    traces.append({'type': 'scatter', 'mode': 'lines', 'name': f'Dev {idx} DDR %', 'yaxis': 'y3',
                                    'x': mon_x, 'y': ddr_y})
                syscore_y = [devices.get(idx, {}).get('sys_core_pct') for _, devices in mon_hist]
                if any(v is not None for v in syscore_y):
                    traces.append({'type': 'scatter', 'mode': 'lines', 'name': f'Dev {idx} sys-core %', 'yaxis': 'y3',
                                    'x': mon_x, 'y': syscore_y})
                core_indices = sorted(
                    {ci for _, devices in mon_hist for ci in (devices.get(idx, {}).get('ai_cores') or {}).keys()},
                    key=int,
                )
                for ci in core_indices:
                    core_y = [(devices.get(idx, {}).get('ai_cores') or {}).get(ci, {}).get('core_utilization_pct')
                              for _, devices in mon_hist]
                    if any(v is not None for v in core_y):
                        traces.append({'type': 'scatter', 'mode': 'lines', 'name': f'Dev {idx} core {ci} %',
                                        'yaxis': 'y3', 'x': mon_x, 'y': core_y})
                    mvm_y = [(devices.get(idx, {}).get('ai_cores') or {}).get(ci, {}).get('mvm_average_utilization_pct')
                             for _, devices in mon_hist]
                    if any(v is not None for v in mvm_y):
                        traces.append({'type': 'scatter', 'mode': 'lines', 'name': f'Dev {idx} core {ci} MVM %',
                                        'yaxis': 'y3', 'x': mon_x, 'y': mvm_y})
    benchmark_stats_plot.update_figure({'data': traces, 'layout': _benchmark_combined_plot_layout()})
    benchmark_no_sources_label.set_visibility(not active)


def _on_benchmark_clear_plot_clicked() -> None:
    """Clear all plot histories and redraw the empty chart."""
    for entry in BENCHMARK_SOURCES.values():
        entry['metrics_history'].clear()
    BENCHMARK_AGGREGATE_HISTORY.clear()
    BENCHMARK_SYSTEM_METRICS_HISTORY.clear()
    MONITOR_STATS_HISTORY.clear()
    _refresh_benchmark_plots()


# Seconds between AxMonitor polls.
MONITOR_METRICS_SAMPLE_INTERVAL_S = 2.0
_monitor_poll_in_flight = False

if not hasattr(core.app.state, 'monitor_stats_history'):
    core.app.state.monitor_stats_history = deque(maxlen=BENCHMARK_METRICS_HISTORY_MAXLEN)
MONITOR_STATS_HISTORY: deque = core.app.state.monitor_stats_history
if not hasattr(core.app.state, 'monitor_available'):
    core.app.state.monitor_available = None
_MONITOR_CHECKBOXES: list = []


async def _fetch_monitor_stats() -> dict:
    """Fetch AxMonitor device statistics from host_server.py.

    Returns:
        dict: The server JSON plus 'reachable': True, or {'reachable': False, 'error': ...}.
    """
    if not HOST_SERVER_URL:
        return {'reachable': False, 'error': 'HOST_SERVER_URL not configured'}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f'{HOST_SERVER_URL}/api/v1/monitor/stats', headers={'X-API-Key': HOST_SERVER_API_KEY})
            resp.raise_for_status()
            result = resp.json()
            result['reachable'] = True
            return result
    except Exception as exc:
        return {'reachable': False, 'error': str(exc)}


# Largest power limit the GUI accepts, in watts.
MONITOR_POWER_LIMIT_MAX_W = 500.0


async def _set_device_power_limit(device_id, power_w) -> tuple[bool, str]:
    """Set the power limit of one device through host_server.py's axdevice endpoint and read it back.

    Args:
        device_id: Device index, a whole number >= 0.
        power_w: Limit in watts between 0 and MONITOR_POWER_LIMIT_MAX_W; 0 turns the limit off.

    Returns:
        tuple[bool, str]: Success flag and a message for the user.
    """
    if not HOST_SERVER_URL:
        return False, 'HOST_SERVER_URL not configured'
    try:
        dev = int(device_id)
        watts = float(power_w)
    except (TypeError, ValueError):
        return False, 'device ID and power must be numbers'
    if dev < 0 or dev != float(device_id):
        return False, 'device ID must be a whole number >= 0'
    if not 0 <= watts <= MONITOR_POWER_LIMIT_MAX_W:
        return False, f'power must be between 0 and {MONITOR_POWER_LIMIT_MAX_W:g} W (0 = off)'
    headers = {'X-API-Key': HOST_SERVER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f'{HOST_SERVER_URL}/api/v1/devices/{dev}/axdevice', headers=headers,
                json={'power_limit_w': watts, 'confirm': True, 'allow_busy': True})
            if resp.status_code != 200:
                return False, f'device {dev}: HTTP {resp.status_code}: {resp.text[:200]}'
            data = resp.json()
            if not data.get('ok'):
                err = next((s.get('stderr') or s.get('stdout') for s in data.get('steps', []) if s.get('returncode') != 0), '')
                return False, f'device {dev}: axdevice failed: {(err or "unknown error")[:200]}'
            back = await client.get(f'{HOST_SERVER_URL}/api/v1/devices/{dev}/axdevice', headers=headers)
            got = back.json().get('power_limit_w') if back.status_code == 200 else None
    except Exception as exc:
        return False, f'device {dev}: {exc}'
    shown = 'off' if got in (None, 'off') and watts == 0 else got
    return True, f'device {dev}: power limit set to {watts:g} W, device reports {shown}'


async def _on_monitor_set_power_clicked(device_input, power_input) -> None:
    """Apply the entered power limit and show the outcome in a toast.

    Args:
        device_input: Number input holding the device index.
        power_input: Number input holding the limit in watts.
    """
    ok, msg = await _set_device_power_limit(device_input.value, power_input.value)
    ui.notify(msg, type='positive' if ok else 'negative')


def _summarize_monitor_device(dev: dict) -> dict:
    """Reduce one device's AxMonitor record to the fields kept in history.

    Args:
        dev (dict): Per-device entry of the monitor stats response.

    Returns:
        dict: Device name, DDR and sys-core utilization, power sensor readings, the raw 'ai_cores' mapping and the mean AI core and MVM utilization (None when no core reports one).
    """
    ai_cores = dev.get('ai_cores') or {}
    core_vals = [c.get('core_utilization_pct') for c in ai_cores.values() if c.get('core_utilization_pct') is not None]
    mvm_vals = [c.get('mvm_average_utilization_pct') for c in ai_cores.values() if c.get('mvm_average_utilization_pct') is not None]
    return {
        'device_name': dev.get('device_name'),
        'ddr_pct': dev.get('ddr_utilization_pct'),
        'power_sensor_0_w': dev.get('power_sensor_0_w'),
        'power_sensor_1_w': dev.get('power_sensor_1_w'),
        'sys_core_pct': dev.get('sys_core_utilization_pct'),
        'avg_core_pct': sum(core_vals) / len(core_vals) if core_vals else None,
        'avg_mvm_pct': sum(mvm_vals) / len(mvm_vals) if mvm_vals else None,
        'ai_cores': ai_cores,
    }


def _compute_monitor_aggregates(devices: dict) -> dict:
    """Average utilization across devices for one history sample.

    Args:
        devices (dict): Device index -> summary from _summarize_monitor_device.

    Returns:
        dict: 'core_pct' and 'mvm_pct' (mean over all AI cores of all devices), 'syscore_pct' and 'ddr_pct' (mean over devices); a value is None when nothing reported it.
    """
    core_vals, mvm_vals, syscore_vals, ddr_vals = [], [], [], []
    for dev in devices.values():
        if dev.get('sys_core_pct') is not None:
            syscore_vals.append(dev['sys_core_pct'])
        if dev.get('ddr_pct') is not None:
            ddr_vals.append(dev['ddr_pct'])
        for core_entry in (dev.get('ai_cores') or {}).values():
            if core_entry.get('core_utilization_pct') is not None:
                core_vals.append(core_entry['core_utilization_pct'])
            if core_entry.get('mvm_average_utilization_pct') is not None:
                mvm_vals.append(core_entry['mvm_average_utilization_pct'])
    return {
        'core_pct': sum(core_vals) / len(core_vals) if core_vals else None,
        'mvm_pct': sum(mvm_vals) / len(mvm_vals) if mvm_vals else None,
        'syscore_pct': sum(syscore_vals) / len(syscore_vals) if syscore_vals else None,
        'ddr_pct': sum(ddr_vals) / len(ddr_vals) if ddr_vals else None,
    }


def _update_monitor_checkbox_availability(available: bool) -> None:
    """Enable or disable the AxMonitor checkboxes.

    Args:
        available (bool): True when AxMonitor is reachable.
    """
    for checkbox in _MONITOR_CHECKBOXES:
        if available:
            checkbox.enable()
        else:
            checkbox.disable()


async def _monitor_stats_tick_async() -> None:
    """Poll AxMonitor once and append the result to MONITOR_STATS_HISTORY.

    The first poll decides whether monitoring is available at all (and sets the checkboxes accordingly); once found unavailable, polling stops for the life of the process. Always clears the in-flight flag.
    """
    global _monitor_poll_in_flight
    try:
        if core.app.state.monitor_available is False:
            return
        result = await _fetch_monitor_stats()
        available = bool(result.get('reachable'))
        if core.app.state.monitor_available is None:
            core.app.state.monitor_available = available
            _update_monitor_checkbox_availability(available)
        if not available:
            return
        raw_devices = result.get('devices') or {}
        devices = {int(idx): _summarize_monitor_device(dev) for idx, dev in raw_devices.items()}
        MONITOR_STATS_HISTORY.append((time.time(), devices))
        _refresh_benchmark_plots()
    finally:
        _monitor_poll_in_flight = False


def _monitor_stats_tick() -> None:
    """Timer callback that starts a monitor poll unless one is still in flight."""
    global _monitor_poll_in_flight
    if _monitor_poll_in_flight:
        return
    _monitor_poll_in_flight = True
    asyncio.create_task(_monitor_stats_tick_async())


def _read_file_bytes(path: str) -> bytes:
    """Read a whole file.

    Args:
        path (str): File path.

    Returns:
        bytes: The file content.
    """
    with open(path, 'rb') as f:
        return f.read()


def _benchmark_ring_buffer_names(frame_dir: str) -> list:
    """List the saved frames of a source.

    Args:
        frame_dir (str): The source's ring buffer directory.

    Returns:
        list: Sorted '.jpg' file names, oldest first; empty if the directory does not exist.
    """
    try:
        return sorted(n for n in os.listdir(frame_dir) if n.endswith('.jpg'))
    except FileNotFoundError:
        return []


def _parse_frame_filename(name: str):
    """Extract the capture timestamp from a ring buffer file name.

    Args:
        name (str): File name of the form '<seq>_<capture ms>.jpg'.

    Returns:
        int | None: The capture time in milliseconds, or None when the name does not parse.
    """
    stem = name[:-4] if name.endswith('.jpg') else name
    try:
        _seq_str, ts_str = stem.split('_', 1)
        return int(ts_str)
    except ValueError:
        return None


@app.get('/benchmark/thumbnail/{source_id}')
def _benchmark_thumbnail_route(source_id: str) -> Response:
    """Serve the newest saved frame of a source as JPEG.

    Returns:
        Response: The image, or 404 when the source is unknown or has no frames.
    """
    entry = BENCHMARK_SOURCES.get(source_id)
    if entry is None:
        return Response(status_code=404)
    names = _benchmark_ring_buffer_names(entry['frame_dir'])
    if not names:
        return Response(status_code=404)
    try:
        data = _read_file_bytes(os.path.join(entry['frame_dir'], names[-1]))
    except FileNotFoundError:
        return Response(status_code=404)
    return Response(content=data, media_type='image/jpeg')


def _benchmark_transcode_frame(data: bytes, preset: str, fmt: str, quality: int):
    """Re-encode a saved frame for the pinned stream.

    Args:
        data (bytes): Saved JPEG frame.
        preset (str): Resolution preset, a key of BENCHMARK_STREAM_RESOLUTION_HEIGHTS.
        fmt (str): Output format, 'jpeg' or 'webp'.
        quality (int): Encode quality, 1 to 100.

    Returns:
        tuple[bytes, bytes]: Encoded frame and its content type; the input and 'image/jpeg' when it cannot be decoded.
    """
    raw = decode_frame(data)
    if raw is None:
        return data, b'image/jpeg'
    target_height = BENCHMARK_STREAM_RESOLUTION_HEIGHTS.get(preset, 0)
    raw = resize_to_height(raw, target_height)
    encoded = encode_frame(raw, fmt, quality)
    content_type = b'image/webp' if fmt == 'webp' else b'image/jpeg'
    return encoded, content_type


@app.get('/benchmark/stream/{source_id}')
async def _benchmark_stream_route(source_id: str, request: Request) -> StreamingResponse:
    """Stream a source's newest frames as multipart/x-mixed-replace.

    Each part carries an X-Capture-Ts header (capture time in ms) when the file name has one. Frames are re-encoded only when the preset, format or quality differ from the saved JPEG defaults. The stream ends when the client disconnects or the source is removed, and the stream settings are re-read on every iteration.

    Args:
        source_id (str): Id of the source.
        request (Request): The incoming request, used to detect disconnects.

    Returns:
        StreamingResponse: The multipart stream.
    """

    frame_dir = os.path.join(BENCHMARK_FRAMES_DIR, source_id)

    async def _generate():
        """Yield one multipart part per new frame, polling the ring buffer at the configured stream FPS."""
        last_served = None
        while True:
            poll_interval_s = 1.0 / _BENCHMARK_STREAM_SETTINGS['fps']
            if await request.is_disconnected() or source_id not in BENCHMARK_SOURCES:
                return
            names = await asyncio.to_thread(_benchmark_ring_buffer_names, frame_dir)
            if not names or names[-1] == last_served:
                await asyncio.sleep(poll_interval_s)
                continue
            name = names[-1]
            try:
                data = await asyncio.to_thread(_read_file_bytes, os.path.join(frame_dir, name))
            except FileNotFoundError:
                await asyncio.sleep(poll_interval_s)
                continue
            last_served = name
            capture_ts_ms = _parse_frame_filename(name)
            preset = _BENCHMARK_STREAM_SETTINGS['resolution_preset']
            fmt = _BENCHMARK_STREAM_SETTINGS['format']
            quality = _BENCHMARK_STREAM_SETTINGS['quality']
            content_type = b'image/jpeg'
            will_transcode = preset != 'native' or fmt != 'jpeg' or quality != BENCHMARK_STREAM_QUALITY
            if will_transcode:
                data, content_type = await asyncio.to_thread(
                    _benchmark_transcode_frame, data, preset, fmt, quality)
            header = b'--frame\r\nContent-Type: ' + content_type + b'\r\n'
            if capture_ts_ms is not None:
                header += f'X-Capture-Ts: {capture_ts_ms}\r\n'.encode()
            header += b'\r\n'
            yield header + data + b'\r\n'
            await asyncio.sleep(poll_interval_s)

    return StreamingResponse(_generate(), media_type='multipart/x-mixed-replace; boundary=frame')


def _build_source_tile(source_id: str, adapter_kind: str, name: str,
                        initial_fps: float = 1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S) -> dict:
    """Create the UI widgets of one source: the tile card and its pinned-stream dialog.

    Clicking the thumbnail opens the dialog, which starts the browser-side stream player; closing it stops the player.

    Args:
        source_id (str): Id of the source; also used as the tile's data-agent-id.
        adapter_kind (str): 'image', 'video' or 'webcam', shown on the tile.
        name (str): Display name.
        initial_fps (float, optional): Initial value of the Target FPS input. Defaults to the preview poll rate.

    Returns:
        dict: The widgets and ids to merge into the source's entry (img, card, labels, target_fps_input, status_icon, backoff_label, inflight_bar, pinned_dialog, pinned_img_id).
    """

    with sources_container:
        with ui.card().classes('w-full q-pa-xs benchmark-tile').style('position: relative') \
                .props(f'data-agent-id="{source_id}"') as card:
            with ui.row().classes('w-full items-center no-wrap gap-2'):
                safe_name = name.replace('"', '&quot;')
                img = ui.image(_BENCHMARK_BLANK_PIXEL).classes('rounded-borders cursor-pointer') \
                    .style('width: 96px; height: 72px; flex-shrink: 0; background: #222') \
                    .props(f'no-transition no-spinner alt="{safe_name}" aria-label="{safe_name}"')
                with ui.column().classes('col gap-0 overflow-hidden'):
                    ui.label(name).classes('text-body2 ellipsis').tooltip(name)
                    ui.label(adapter_kind).classes('text-caption text-grey')
                    with ui.row().classes('items-center no-wrap gap-1'):
                        fps_label = ui.label('-- fps').classes('text-caption')
                        target_fps_input = ui.number(
                            label=f'Target FPS: {name}',
                            value=round(initial_fps, 1), min=0.1, max=1000, step=1,
                            on_change=lambda e, sid=source_id: _on_source_target_fps_changed(sid, e.value),
                        ).props('dense borderless').classes('text-caption target-fps-input') \
                            .style('width: 44px;') \
                            .tooltip('Target capture fps for this source -- editable live, '
                                     'takes effect on the very next frame (the up/down '
                                     'arrows step by 1). Actual throughput may still be '
                                     'lower if AIMD backoff (÷X.X badge, bottom-left) is '
                                     'currently throttling it.')
                    status_label = ui.label('starting...').classes('text-caption text-grey')
                    infer_label = ui.label('no inference endpoint configured').classes('text-caption text-blue ellipsis')
                    with infer_label:
                        infer_tooltip = ui.tooltip('')
                ui.button(icon='close', on_click=lambda: _benchmark_remove_source(source_id)) \
                    .props('flat dense round size=sm').tooltip('Remove source')
            status_icon = ui.icon('check_circle', size='14px', color='green') \
                .style('position: absolute; right: 6px; bottom: 6px;') \
                .tooltip('Check: inference running cleanly, no errors. Question mark: '
                         'inference errors have occurred. Cross: this source is '
                         'dropping frames right now because its backpressure queue is '
                         'full -- raise "Backpressure cap" in Advanced Settings (right '
                         'drawer) if this happens often.')
            backoff_label = ui.label('').classes('text-caption text-orange') \
                .style('position: absolute; left: 6px; bottom: 6px; font-size: 9px; '
                       'line-height: 1; opacity: 0.85;') \
                .tooltip('Backend is backlogged -- this source is pacing itself down '
                         'by this factor (AIMD-style backoff against host_server.py\'s '
                         '/queue-stats) instead of flooding an already-congested pipeline.')
            backoff_label.set_visibility(False)
            inflight_bar = ui.linear_progress(value=0.0, show_value=False, size='3px') \
                .props('rounded') \
                .style('position: absolute; left: 6px; bottom: 0px; '
                       'width: calc(100% - 12px);') \
                .tooltip('In-flight inference requests, as a fraction of the '
                         '"Backpressure cap" (Advanced Settings, right drawer). '
                         'Full bar = this source is at its cap and starting to '
                         'drop new frames.')
            inflight_bar.set_visibility(False)

    pinned_img_id = f'pinned-stream-{source_id}'
    with ui.dialog() as pinned_dialog, ui.card().classes('q-pa-sm').style('max-width: 95vw;') as pinned_card:
        with ui.row().classes('w-full items-center justify-between q-mb-xs'):
            ui.label(name).classes('text-subtitle2')
            ui.button(icon='close', on_click=pinned_dialog.close).props('flat dense round size=sm')
        ui.html(
            '<div style="position: relative; height: 70vh; max-height: 780px; '
            'aspect-ratio: 16 / 9; width: 100%;">'
            f'<img id="{pinned_img_id}" '
            'style="height: 100%; width: 100%; background: #000; '
            'object-fit: contain; display: block;" />'
            f'<div id="{pinned_img_id}-spinner" class="pinned-stream-spinner-overlay">'
            '<div class="pinned-stream-spinner-ring"></div>'
            f'<div id="{pinned_img_id}-status" class="pinned-stream-status-text"></div>'
            '</div>'
            '<img src="/gui-static/axelera-logo-mark.png" class="pinned-stream-watermark" />'
            '</div>'
        )

    def _open_pinned() -> None:
        """Start the pinned stream player in the browser and open the dialog."""
        ui.run_javascript(f"window.__pinnedStreamStart('{pinned_img_id}', '/benchmark/stream/{source_id}');")
        pinned_dialog.open()

    def _close_pinned() -> None:
        """Stop the pinned stream player in the browser."""
        ui.run_javascript(f"window.__pinnedStreamStop('{pinned_img_id}');")

    img.on('click', _open_pinned)
    pinned_dialog.on_value_change(lambda e: None if e.value else _close_pinned())

    return {
        'img': img,
        'card': card,
        'fps_label': fps_label,
        'target_fps_input': target_fps_input,
        'status_label': status_label,
        'infer_label': infer_label,
        'infer_tooltip': infer_tooltip,
        'status_icon': status_icon,
        'backoff_label': backoff_label,
        'inflight_bar': inflight_bar,
        'pinned_dialog': pinned_dialog,
        'pinned_img_id': pinned_img_id,
    }


def _benchmark_add_source(adapter_kind: str, adapter_path, name: str, *,
                           poll_interval_s: float = BENCHMARK_PREVIEW_POLL_INTERVAL_S) -> None:
    """Validate a source, build its tile and start its worker process.

    The adapter is opened and closed once first so a bad path or busy device fails with a toast instead of a dead worker. The worker is spawned with the current stream settings, endpoints and pipeline ids.

    Args:
        adapter_kind (str): 'image', 'video' or 'webcam'.
        adapter_path: File path or webcam device.
        name (str): Display name.
        poll_interval_s (float, optional): Seconds between captures. Defaults to BENCHMARK_PREVIEW_POLL_INTERVAL_S.
    """
    try:
        probe = make_adapter(adapter_kind, adapter_path)
        probe.open()
        probe.close()
    except SourceAdapterError as exc:
        ui.notify(f'could not open {name}: {exc}', type='negative')
        return
    core.app.state.benchmark_source_seq += 1
    source_id = f'src-{core.app.state.benchmark_source_seq}'

    capture_poll_interval = MP_CONTEXT.Value('d', poll_interval_s)

    tile = _build_source_tile(source_id, adapter_kind, name, initial_fps=1.0 / poll_interval_s)

    frame_dir = os.path.join(BENCHMARK_FRAMES_DIR, source_id)
    shutil.rmtree(frame_dir, ignore_errors=True)

    entry = {
        'adapter_kind': adapter_kind,
        'adapter_path': adapter_path,
        'kind': adapter_kind,
        'name': name,
        'frame_dir': frame_dir,
        'process': None,
        'stop_event': None,
        'metrics_queue': None,
        'latest_metrics': None,
        'last_thumbnail_refresh_ts': 0.0,
        'poll_interval_value': capture_poll_interval,
        'metrics_history': deque(maxlen=_benchmark_metrics_history_maxlen),
    }
    entry.update(tile)
    BENCHMARK_SOURCES[source_id] = entry

    stop_event = MP_CONTEXT.Event()
    metrics_queue = MP_CONTEXT.Queue(maxsize=1)
    process = MP_CONTEXT.Process(
        target=run_source_worker,
        kwargs=dict(
            source_id=source_id,
            adapter_kind=adapter_kind,
            adapter_path=adapter_path,
            frame_dir=frame_dir,
            poll_interval_value=capture_poll_interval,
            endpoints=list(_benchmark_endpoints),
            ring_buffer_frames=BENCHMARK_RING_BUFFER_FRAMES,
            stream_max_width_px=_BENCHMARK_STREAM_SETTINGS['max_width_px'],
            max_pending_inflight=_BENCHMARK_STREAM_SETTINGS['max_pending_inflight'],
            request_timeout_sec=_BENCHMARK_STREAM_SETTINGS['request_timeout_sec'],
            aimd_backoff_enabled=_BENCHMARK_STREAM_SETTINGS['aimd_backoff_enabled'],
            render_interval_s=1.0 / _BENCHMARK_STREAM_SETTINGS['fps'],
            metrics_queue=metrics_queue,
            stop_event=stop_event,
            pipeline_ids=list(_benchmark_pipeline_ids),
            host_server_url=HOST_SERVER_URL,
            host_server_api_key=HOST_SERVER_API_KEY,
        ),
    )
    process.start()
    entry['process'] = process
    entry['stop_event'] = stop_event
    entry['metrics_queue'] = metrics_queue
    if _benchmark_endpoints:
        entry['infer_label'].set_text('infer: starting...')
    _update_benchmark_source_count()


def _rehydrate_benchmark_sources() -> None:
    """Rebuild the tiles of sources that already exist, for a newly loaded page."""
    for source_id, entry in BENCHMARK_SOURCES.items():
        poll_interval_value = entry.get('poll_interval_value')
        initial_fps = (1.0 / poll_interval_value.value) if poll_interval_value is not None \
            else 1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S
        tile = _build_source_tile(source_id, entry['adapter_kind'], entry['name'], initial_fps=initial_fps)
        entry.update(tile)
    _update_benchmark_source_count()


def _on_benchmark_add_file_clicked() -> None:
    """Open the dialog for adding file sources.

    Offers a folder browser starting at the test image directory, a copy count and a target FPS (capped at BENCHMARK_IMAGE_SOURCE_MAX_FPS for images, 60 for videos), and a button that fetches the standard test media via host_server.py.
    """
    start_dir = BENCHMARK_SOURCE_DEFAULT_DIR if os.path.isdir(BENCHMARK_SOURCE_DEFAULT_DIR) else os.path.dirname(__file__)
    state = {'dir': start_dir, 'selected': None}
    with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            ui.label('Add source from file').classes('text-subtitle1 font-semibold')
            with ui.row().classes('items-center gap-1 no-wrap'):
                fetch_status_label = ui.label('').classes('text-caption text-grey')
                fetch_status_label.set_visibility(False)
                fetch_spinner = ui.spinner(size='1em')
                fetch_spinner.set_visibility(False)
                fetch_media_btn = ui.button(icon='cloud_download', on_click=lambda: _on_fetch_media_clicked()) \
                    .props('dense flat round size=sm').tooltip(
                        'Fetch standard test media: downloads/transcodes the traffic, '
                        'intersection and dancing sample videos (480p/720p/1080p) into this '
                        'folder on the server -- skips any file already present'
                    )
        path_label = ui.label(state['dir']).classes('text-caption text-grey q-mb-sm')
        file_select = ui.select({}, label='File / folder').props('dense outlined').classes('w-full')
        count_input = ui.number('Count', value=1, min=1, max=50, format='%.0f') \
            .props('dense outlined').classes('w-full q-mt-sm') \
            .tooltip('Add this many identical copies of the selected source in one go')
        fps_input = ui.number('FPS', value=1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S, min=5, max=60) \
            .props('dense outlined').classes('w-full q-mt-sm') \
            .tooltip('How fast this source is re-captured and fed to inference (image: re-reads the same file; video: frame-read rate)')

        def _refresh() -> None:
            """List the current folder in the picker and clear the selection."""
            options = {}
            parent = os.path.dirname(state['dir'].rstrip('/'))
            if parent and parent != state['dir'].rstrip('/'):
                options['..'] = '.. (up)'
            for entry_name, is_dir in _benchmark_list_dir(state['dir']):
                options[entry_name] = f'{entry_name}/' if is_dir else entry_name
            file_select.set_options(options, value=None)
            path_label.set_text(state['dir'])
            state['selected'] = None
            open_btn.set_enabled(False)

        async def _on_fetch_media_clicked() -> None:
            """Fetch the standard test media, showing progress, then summarize the result and refresh the folder listing."""
            fetch_media_btn.set_enabled(False)
            fetch_spinner.set_visibility(True)
            fetch_status_label.set_visibility(True)
            fetch_status_label.set_text('starting...')
            try:
                start_result = await _start_benchmark_media_fetch()
                if not start_result.get('reachable'):
                    ui.notify(f"host_server unreachable: {start_result.get('error', '?')}", type='negative')
                    return
                if 'error' in start_result:
                    ui.notify(f"fetch test media failed: {start_result['error']}", type='negative')
                    return
                status: dict = {}
                while True:
                    await asyncio.sleep(0.75)
                    status = await _poll_benchmark_media_status()
                    if not status.get('reachable'):
                        ui.notify(f"host_server unreachable: {status.get('error', '?')}", type='negative')
                        return
                    if 'error' in status:
                        ui.notify(f"fetch test media failed: {status['error']}", type='negative')
                        return
                    done_count = len(status.get('results', []))
                    total = status.get('total') or 9
                    current_file = status.get('current_file')
                    stage = status.get('stage')
                    if current_file and stage:
                        stage_label = _BENCHMARK_MEDIA_STAGE_LABELS.get(stage, stage)
                        fetch_status_label.set_text(f'{stage_label} {current_file} ({done_count}/{total})')
                    else:
                        fetch_status_label.set_text(f'{done_count}/{total} done')
                    if not status.get('running'):
                        break
                counts: dict[str, int] = {}
                errors = []
                for r in status.get('results', []):
                    counts[r['status']] = counts.get(r['status'], 0) + 1
                    if r['status'] == 'error':
                        errors.append(f"{r['file']}: {r.get('detail', '?')}")
                summary = ', '.join(f'{v} {k}' for k, v in counts.items())
                if errors:
                    ui.notify(f'Fetch test media: {summary} -- {"; ".join(errors[:2])}', type='warning', multi_line=True)
                else:
                    ui.notify(f'Fetch test media: {summary}', type='positive')
                if os.path.isdir(BENCHMARK_SOURCE_DEFAULT_DIR):
                    state['dir'] = BENCHMARK_SOURCE_DEFAULT_DIR
                _refresh()
            finally:
                fetch_media_btn.set_enabled(True)
                fetch_spinner.set_visibility(False)
                fetch_status_label.set_visibility(False)

        def _on_select(e) -> None:
            """Handle a picker selection.

            '..' and folders navigate; a supported image or video file becomes the selection and sets the FPS limit for its type; anything else shows a warning.

            Args:
                e: Select change event; e.value is the chosen entry name.
            """
            name = e.value
            if not name:
                return
            if name == '..':
                state['dir'] = os.path.dirname(state['dir'].rstrip('/')) or '/'
                _refresh()
                return
            full = os.path.join(state['dir'], name)
            if os.path.isdir(full):
                state['dir'] = full
                _refresh()
                return
            ext = os.path.splitext(full)[1].lower()
            if ext not in BENCHMARK_IMAGE_EXTENSIONS and ext not in BENCHMARK_VIDEO_EXTENSIONS:
                ui.notify(f'unsupported file type: {ext or "(none)"}', type='warning')
                open_btn.set_enabled(False)
                return
            state['selected'] = full
            open_btn.set_enabled(True)
            is_image = ext in BENCHMARK_IMAGE_EXTENSIONS
            new_max = BENCHMARK_IMAGE_SOURCE_MAX_FPS if is_image else 60
            fps_input.max = new_max
            if not is_image and (fps_input.value or 0) > new_max:
                fps_input.set_value(new_max)

        file_select.on_value_change(_on_select)

        def _on_open() -> None:
            """Add the selected file as 'count' sources at the chosen FPS and close the dialog."""
            full = state['selected']
            if not full:
                return
            ext = os.path.splitext(full)[1].lower()
            is_image = ext in BENCHMARK_IMAGE_EXTENSIONS
            kind = 'image' if is_image else 'video'
            base_name = os.path.basename(full)
            count = max(1, int(count_input.value or 1))
            fps = float(fps_input.value or (1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S))
            fps = min(fps, BENCHMARK_IMAGE_SOURCE_MAX_FPS if is_image else 60)
            poll_interval_s = 1.0 / fps
            for i in range(count):
                name = base_name if count == 1 else f'{base_name} #{i + 1}'
                _benchmark_add_source(kind, full, name, poll_interval_s=poll_interval_s)
            dialog.close()

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            open_btn = ui.button('Open', on_click=_on_open)
            open_btn.set_enabled(False)
    _refresh()
    dialog.open()


def _on_benchmark_add_webcam_clicked() -> None:
    """Open the dialog for adding a webcam source."""
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Add webcam source').classes('text-subtitle1 font-semibold')
        device_select = ui.select({}, label='Device').props('dense outlined').classes('w-full')
        fps_input = ui.number('FPS', value=1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S, min=1, max=60) \
            .props('dense outlined').classes('w-full q-mt-sm')

        def _refresh_devices() -> None:
            """Reload the webcam device list, selecting the first device."""
            devices = WebcamAdapterCV.list_devices()
            if not devices:
                device_select.set_options({}, value=None)
                ui.notify('no webcam devices found on this host', type='warning')
                return
            device_select.set_options({d.path: d.display_name for d in devices}, value=devices[0].path)

        def _on_add() -> None:
            """Add the selected webcam at the chosen FPS and close the dialog."""
            path = device_select.value
            if not path:
                return
            fps = float(fps_input.value or (1.0 / BENCHMARK_PREVIEW_POLL_INTERVAL_S))
            _benchmark_add_source('webcam', path, WebcamAdapterCV(path).display_name,
                                   poll_interval_s=1.0 / fps)
            dialog.close()

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Refresh', icon='refresh', on_click=_refresh_devices).props('flat')
            ui.button('Add', on_click=_on_add)
    _refresh_devices()
    dialog.open()



