"""Per-source capture and inference worker of the Benchmarking tab, run in its own OS process.

Exposes run_source_worker() (process entry point), make_adapter() and MP_CONTEXT. Each worker captures frames, optionally pushes them to AxVisionClient, draws results and writes JPEGs to an on-disk ring buffer.

Note:
    Workers are started through MP_CONTEXT ('spawn'), so the child imports this module afresh: keep it free of NiceGUI imports and import-time side effects. Frames never cross the process boundary (the parent reads the ring buffer by filename); only small metrics snapshots go back through a maxsize=1 queue that holds the latest one.
"""

from __future__ import annotations

import collections
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters import ImageAdapterCV, SourceAdapterError, VideoFileAdapterCV, WebcamAdapterCV
from adapters.common.rendering import draw_detections, draw_embeddings, draw_face, draw_keypoints, draw_segmentation, evict_oldest, resize_frame, save_frame
from inference import AxVisionClient

MP_CONTEXT = multiprocessing.get_context('spawn')

# Minimum seconds between metrics snapshots put on the queue.
_PUBLISH_INTERVAL_S = 0.2

# Default minimum seconds between drawn and saved frames (24 per second).
_RENDER_INTERVAL_S = 1.0 / 24.0

# Rates are events in this trailing window divided by the window length, so a burst after a stall is not reported as an extreme rate.
_FPS_RATE_WINDOW_S = 2.0

# A stream must be at least this old before a rate is reported.
_MIN_FPS_WINDOW_S = 0.05

# Default cap on in-flight inference requests; each holds a copy of the raw frame until its result arrives.
_MAX_PENDING_INFLIGHT = 32

# Default client-side gRPC deadline in seconds.
_REQUEST_TIMEOUT_SEC = 20.0

# Seconds between queue-stats polls.
_QUEUE_STATS_POLL_INTERVAL_S = 2.0

# Backoff multiplier growth per congested round, and shrink per recovery step.
_QUEUE_STATS_BACKOFF_FACTOR = 1.5
_QUEUE_STATS_RECOVERY_FACTOR = _QUEUE_STATS_BACKOFF_FACTOR
# Upper bound of the capture-interval multiplier.
_QUEUE_STATS_MAX_BACKOFF_MULTIPLIER = 4.0
# Clean rounds required before one recovery step.
_QUEUE_STATS_RECOVERY_STREAK_REQUIRED = 1

# Queue fill fraction at or above which a queue counts as congested.
_QUEUE_STATS_OCCUPANCY_THRESHOLD = 0.75


def _is_congested_sample(payload: dict) -> bool:
    """Judge whether one /queue-stats sample shows the backend under backpressure.

    A snapshot judgement, not a trend; the caller accumulates samples into the backoff decision.

    Args:
        payload (dict): Parsed queue-stats JSON with optional keys 'healthy', 'node_queues' (entries with input_used/input_depth/result_used/result_depth), 'imdecode_queue_used' and 'imdecode_queue_depth'.

    Returns:
        bool: True if the server is unhealthy, or any node queue or the imdecode queue is filled to at least _QUEUE_STATS_OCCUPANCY_THRESHOLD of its depth.
    """
    if not payload.get('healthy', True):
        return True
    for node in payload.get('node_queues', []):
        for used_key, depth_key in (('input_used', 'input_depth'), ('result_used', 'result_depth')):
            depth = node.get(depth_key) or 0
            if depth > 0 and (node.get(used_key, 0) / depth) >= _QUEUE_STATS_OCCUPANCY_THRESHOLD:
                return True
    imdecode_depth = payload.get('imdecode_queue_depth') or 0
    if imdecode_depth > 0 and (payload.get('imdecode_queue_used', 0) / imdecode_depth) >= _QUEUE_STATS_OCCUPANCY_THRESHOLD:
        return True
    return False


def make_adapter(kind: str, path):
    """Build a fresh, unopened source adapter from a picklable (kind, path) pair.

    Taking a pair instead of an adapter lets it be passed to a spawned process (an opened adapter holds a live capture handle).

    Args:
        kind (str): 'image', 'video' or 'webcam'.
        path: Image or video file path, or webcam device, passed to the adapter.

    Returns:
        ImageAdapterCV | VideoFileAdapterCV | WebcamAdapterCV: The adapter for `kind`.

    Raises:
        ValueError: If `kind` is not one of the above.
    """
    if kind == 'image':
        return ImageAdapterCV(path)
    if kind == 'video':
        return VideoFileAdapterCV(path)
    if kind == 'webcam':
        return WebcamAdapterCV(path)
    raise ValueError(f'unknown adapter kind: {kind!r}')


def _publish(queue: multiprocessing.Queue, snapshot: dict) -> None:
    """Replace whatever is queued with a metrics snapshot, without blocking.

    Errors from the queue are swallowed; the next snapshot supersedes a lost one.

    Args:
        queue (multiprocessing.Queue): The maxsize=1 metrics queue.
        snapshot (dict): Metrics snapshot to publish.
    """
    try:
        queue.get_nowait()
    except Exception:
        pass
    try:
        queue.put_nowait(snapshot)
    except Exception:
        pass


def run_source_worker(
    *,
    source_id: str,
    adapter_kind: str,
    adapter_path,
    frame_dir: str,
    poll_interval_value,
    endpoints: list,
    ring_buffer_frames: int,
    stream_max_width_px: int,
    metrics_queue: multiprocessing.Queue,
    stop_event,
    max_pending_inflight: int = _MAX_PENDING_INFLIGHT,
    request_timeout_sec: float = _REQUEST_TIMEOUT_SEC,
    render_interval_s: float = _RENDER_INTERVAL_S,
    pipeline_ids: tuple = (),
    host_server_url: str = '',
    host_server_api_key: str = '',
    aimd_backoff_enabled: bool = True,
) -> None:
    """Run one Benchmarking source from capture to ring-buffer output until stopped.

    Opens the adapter, then loops: read a frame, push it for inference (or, without endpoints, resize and save it directly), update the rate counters and publish metrics, and sleep until the next capture is due. Returns when stop_event is set, the adapter fails or the stream ends. On exit the inference stream, client and adapter are closed.

    With endpoints, the saved frames are the raw frames with any detections drawn on, written at most once per render_interval_s. A background thread polls host_server.py queue-stats and scales the capture interval by a backoff multiplier while the backend looks congested.

    Args:
        source_id (str): Id used in log lines and the backoff thread name.
        adapter_kind (str): 'image', 'video' or 'webcam'; see make_adapter().
        adapter_path: Path or device handed to the adapter.
        frame_dir (str): Directory of the JPEG ring buffer this source writes.
        poll_interval_value (multiprocessing.Value): Shared float holding the target seconds between captures. Read on every loop iteration, so the parent can retarget a running source.
        endpoints (list): Inference endpoints for AxVisionClient. Empty means capture-only: no inference and no inference metrics.
        ring_buffer_frames (int): Number of frames kept in frame_dir.
        stream_max_width_px (int): Maximum width of saved frames in pixels, passed to resize_frame.
        metrics_queue (multiprocessing.Queue): Maxsize=1 queue carrying the latest snapshot to the parent.
        stop_event (multiprocessing.Event): Set by the parent to stop the worker.
        max_pending_inflight (int, optional): Cap on submitted-but-unanswered requests; new frames are skipped at the cap, and a value <= 0 disables it. Defaults to _MAX_PENDING_INFLIGHT.
        request_timeout_sec (float, optional): Client-side gRPC call deadline in seconds. Defaults to _REQUEST_TIMEOUT_SEC.
        render_interval_s (float, optional): Minimum seconds between rendered and saved frames when inferring. Defaults to _RENDER_INTERVAL_S.
        pipeline_ids (tuple, optional): Pipeline ids whose queue-stats are polled for backoff.
        host_server_url (str, optional): Base URL of host_server.py for those polls.
        host_server_api_key (str, optional): Sent as the X-API-Key header on those polls.
        aimd_backoff_enabled (bool, optional): Allow the backoff thread, which also needs pipeline_ids and host_server_url. Defaults to True.

    Note:
        The `state` dict is shared by the capture loop (main thread), the `_on_result` callback (called from the inference client's thread) and the backoff thread, and is guarded by `lock`.
    """

    try:
        adapter = make_adapter(adapter_kind, adapter_path)
        adapter.open()
    except SourceAdapterError as exc:
        _publish(metrics_queue, {'status': f'error: {exc}'})
        return

    lock = threading.Lock()
    state = {
        'capture_ts': collections.deque(),
        'infer_ts': collections.deque(),
        'capture_window_start': None,
        'infer_window_start': None,
        # Submit times, popped in order to measure latency (results may arrive unordered, so this is approximate).
        'infer_submit_ts': collections.deque(),
        'infer_errors': 0,
        'last_latency_ms': None,
        'last_det_count': 0,
        'status': 'live',
        'has_frame': False,
        'drop_reason': '',
        'backpressure_active': False,
        # local_seq -> (raw frame copy, capture timestamp) for requests awaiting a result.
        'pending': {},
        'last_publish_ts': 0.0,
        'last_render_ts': 0.0,
        'last_capture_fps': 0.0,
        'last_infer_fps': 0.0,
        # Scales the capture interval; 1.0 means no backoff.
        'backoff_multiplier': 1.0,
    }

    def _maybe_publish(force: bool = False) -> None:
        """Publish a metrics snapshot unless one went out within _PUBLISH_INTERVAL_S.

        Recomputes capture and inference rates first. Inference fields are included only when endpoints are configured.

        Args:
            force (bool, optional): Publish even if the interval has not elapsed. Defaults to False.
        """
        now = time.monotonic()

        def _rate_from_window(events: collections.deque, start_key: str) -> Optional[float]:
            """Return events per second over the trailing _FPS_RATE_WINDOW_S window.

            Drops timestamps older than the window from `events` in place.

            Args:
                events (collections.deque): Monotonic timestamps of events.
                start_key (str): Key in `state` holding the time of the stream's first event.

            Returns:
                float | None: The rate, or None while the stream is younger than _MIN_FPS_WINDOW_S or has no first event yet.
            """
            cutoff = now - _FPS_RATE_WINDOW_S
            while events and events[0] < cutoff:
                events.popleft()
            start = state[start_key]
            if start is None:
                return None
            elapsed = now - start
            if elapsed < _MIN_FPS_WINDOW_S:
                return None
            return len(events) / min(_FPS_RATE_WINDOW_S, elapsed)

        with lock:
            if not force and (now - state['last_publish_ts']) < _PUBLISH_INTERVAL_S:
                return
            state['last_publish_ts'] = now
            rate = _rate_from_window(state['capture_ts'], 'capture_window_start')
            if rate is not None:
                state['last_capture_fps'] = rate
            capture_fps = state['last_capture_fps']
            rate = _rate_from_window(state['infer_ts'], 'infer_window_start')
            if rate is not None:
                state['last_infer_fps'] = rate
            infer_fps = state['last_infer_fps']
            snapshot = {
                'status': state['status'],
                'capture_fps': capture_fps,
                'has_frame': state['has_frame'],
            }
            if endpoints:
                snapshot.update(
                    infer_fps=infer_fps,
                    latency_ms=state['last_latency_ms'],
                    det_count=state['last_det_count'],
                    infer_errors=state['infer_errors'],
                    drop_reason=state['drop_reason'],
                    backpressure_active=state['backpressure_active'],
                    backoff_multiplier=state['backoff_multiplier'],
                    inflight=len(state['pending']),
                    inflight_cap=max_pending_inflight,
                )
        _publish(metrics_queue, snapshot)

    infer_client: Optional[AxVisionClient] = None
    infer_stream = None

    if endpoints:
        infer_client = AxVisionClient(list(endpoints))

        def _on_result(local_seq: int, response) -> None:
            """Handle one inference response from the client stream.

            Matches the response to its pending frame, updates latency, error, detection and rate counters, and, at most once per render_interval_s for a successful response, draws the detections on the frame and saves it into the ring buffer.

            Args:
                local_seq (int): Sequence number the frame was pushed with.
                response: Inference response; a non-zero `status` marks a dropped frame.
            """
            with lock:
                pending_entry = state['pending'].pop(local_seq, None)
            if pending_entry is None:
                return
            raw, capture_ts = pending_entry
            now = time.monotonic()
            with lock:
                if state['infer_submit_ts']:
                    state['last_latency_ms'] = (now - state['infer_submit_ts'].popleft()) * 1000.0
            dropped = bool(getattr(response, 'status', 0))
            det_count = 0
            if dropped:
                drop_reason = getattr(response, 'status_message', '') or ''
                with lock:
                    state['infer_errors'] += 1
                    state['last_det_count'] = 0
                    state['drop_reason'] = drop_reason
                print(f'[benchmark:{source_id}] frame dropped: {drop_reason}', flush=True)
            else:
                detections = list(response.detections)
                det_count = len(detections)
                with lock:
                    state['last_det_count'] = det_count
                    state['drop_reason'] = ''
            with lock:
                if state['infer_window_start'] is None:
                    state['infer_window_start'] = now
                state['infer_ts'].append(now)
                should_render = (not dropped) and (now - state['last_render_ts']) >= render_interval_s
                if should_render:
                    state['last_render_ts'] = now
            if should_render:
                if det_count:
                    draw_detections(raw, detections)
                    draw_keypoints(raw, detections)
                    draw_segmentation(raw, detections)
                    draw_face(raw, detections)
                    draw_embeddings(raw, detections)
                raw = resize_frame(raw, stream_max_width_px)
                name = f'{local_seq:08d}_{int(capture_ts * 1000):014d}.jpg'
                save_frame(frame_dir, name, raw)
                evict_oldest(frame_dir, name, ring_buffer_frames)
                with lock:
                    state['has_frame'] = True
            _maybe_publish()

        infer_stream = infer_client.open_stream(
            on_result=_on_result, ordered=False, request_timeout_sec=request_timeout_sec)

        if pipeline_ids and host_server_url and aimd_backoff_enabled:
            def _run_queue_stats_backoff_loop() -> None:
                """Poll queue-stats and adjust the capture backoff multiplier until stop_event is set.

                Each round queries every pipeline id and ignores failed requests; a round with no successful reply changes nothing. A congested round multiplies backoff_multiplier by _QUEUE_STATS_BACKOFF_FACTOR (capped at _QUEUE_STATS_MAX_BACKOFF_MULTIPLIER). After _QUEUE_STATS_RECOVERY_STREAK_REQUIRED clean rounds it is divided by _QUEUE_STATS_RECOVERY_FACTOR (floored at 1.0). Logs each change.
                """
                headers = {'X-API-Key': host_server_api_key}
                clean_streak = 0
                with httpx.Client(timeout=3.0) as client:
                    while not stop_event.wait(_QUEUE_STATS_POLL_INTERVAL_S):
                        congested = False
                        saw_any = False
                        for pid in pipeline_ids:
                            try:
                                resp = client.get(f'{host_server_url}/api/v1/pipelines/{pid}/queue-stats',
                                                   headers=headers)
                            except Exception:
                                continue
                            if resp.status_code != 200:
                                continue
                            saw_any = True
                            if _is_congested_sample(resp.json()):
                                congested = True
                        if not saw_any:
                            continue
                        with lock:
                            prev_multiplier = state['backoff_multiplier']
                            if congested:
                                clean_streak = 0
                                state['backoff_multiplier'] = min(
                                    state['backoff_multiplier'] * _QUEUE_STATS_BACKOFF_FACTOR,
                                    _QUEUE_STATS_MAX_BACKOFF_MULTIPLIER,
                                )
                            else:
                                clean_streak += 1
                                if clean_streak >= _QUEUE_STATS_RECOVERY_STREAK_REQUIRED:
                                    clean_streak = 0
                                    state['backoff_multiplier'] = max(
                                        state['backoff_multiplier'] / _QUEUE_STATS_RECOVERY_FACTOR, 1.0,
                                    )
                            if state['backoff_multiplier'] != prev_multiplier:
                                print(f'[benchmark:{source_id}] AIMD backoff_multiplier '
                                      f'{prev_multiplier:.3f} -> {state["backoff_multiplier"]:.3f} '
                                      f'(congested={congested}, clean_streak={clean_streak})', flush=True)

            threading.Thread(target=_run_queue_stats_backoff_loop, daemon=True,
                              name=f'{source_id}-backoff').start()

    capture_seq = 0
    push_seq = 0
    try:
        while not stop_event.is_set():
            try:
                frame = adapter.read_frame(need_encoded=bool(endpoints))
            except SourceAdapterError as exc:
                with lock:
                    state['status'] = f'error: {exc}'
                _maybe_publish(force=True)
                break
            if frame is None:
                with lock:
                    state['status'] = 'end of stream'
                _maybe_publish(force=True)
                break
            capture_ts = time.monotonic()
            capture_seq += 1
            if infer_stream is not None:
                with lock:
                    backlog = len(state['pending'])
                if max_pending_inflight > 0 and backlog >= max_pending_inflight:
                    with lock:
                        state['drop_reason'] = f'queue full ({backlog})'
                        state['backpressure_active'] = True
                    _maybe_publish()
                else:
                    with lock:
                        state['backpressure_active'] = False
                    seq = push_seq
                    push_seq += 1
                    with lock:
                        state['pending'][seq] = (frame.raw.copy(), capture_ts)
                        state['infer_submit_ts'].append(time.monotonic())
                    try:
                        infer_stream.push(frame.encoded, request_id=str(seq))
                    except Exception as exc:
                        with lock:
                            state['pending'].pop(seq, None)
                            if state['infer_submit_ts']:
                                state['infer_submit_ts'].pop()
                            state['drop_reason'] = f'submit error: {exc}'
                        _maybe_publish(force=True)
            else:
                resized = resize_frame(frame.raw, stream_max_width_px)
                name = f'{capture_seq:08d}_{int(capture_ts * 1000):014d}.jpg'
                save_frame(frame_dir, name, resized)
                evict_oldest(frame_dir, name, ring_buffer_frames)
                with lock:
                    state['has_frame'] = True
            with lock:
                if state['capture_window_start'] is None:
                    state['capture_window_start'] = capture_ts
                state['capture_ts'].append(capture_ts)
            _maybe_publish()
            with lock:
                backoff_multiplier = state['backoff_multiplier']
            next_due = capture_ts + poll_interval_value.value * backoff_multiplier
            remaining = next_due - time.monotonic()
            if remaining > 0:
                stop_event.wait(remaining)
    finally:
        if infer_stream is not None:
            try:
                infer_stream.close(timeout=2.0)
            except Exception:
                pass
        if infer_client is not None:
            try:
                infer_client.close()
            except Exception:
                pass
        try:
            adapter.close()
        except SourceAdapterError:
            pass
