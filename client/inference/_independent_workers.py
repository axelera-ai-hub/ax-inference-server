"""Worker-process entry points and a multi-process benchmark for the inference clients.

Holds the loop run inside each _CrossProcessEngine worker (_node_worker_main) and the
IndependentWorkersBenchmark that drives several client processes in parallel.
"""
from __future__ import annotations

import multiprocessing
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ._shm_ring import unpack_call

_READER_QUEUE_MAXSIZE = 64

_FLUSH_TICK_SEC = 0.001


@dataclass
class WorkerResult:
    """Outcome of one benchmark worker process.

    Attributes:
        worker_id (int): Index of the worker.
        num_endpoints (int): Endpoints the worker targeted.
        requests_per_endpoint (int): Requests planned per endpoint.
        completed (int): Responses received, including errors and warmup.
        expected (int): Responses expected (requests_per_endpoint * num_endpoints).
        errors (int): Responses with a non-zero status.
        client_side_errors (int): Errors whose message starts with 'client-side '.
        server_side_errors (int): Errors reported by the server.
        elapsed_sec (float): Seconds from the first post-warmup response to the end of the run.
        throughput_rps (float): Post-warmup responses per second over elapsed_sec.
        server_side_messages (dict): Up to 5 distinct server error messages with their counts.
        timed_out (bool): True if not all expected responses arrived before the deadline.
    """

    worker_id: int
    num_endpoints: int
    requests_per_endpoint: int
    completed: int
    expected: int
    errors: int
    client_side_errors: int
    server_side_errors: int
    elapsed_sec: float
    throughput_rps: float
    server_side_messages: dict = field(default_factory=dict)
    timed_out: bool = False


def _try_put_until_stopped(
    q: "queue.Queue", item, stop_event: threading.Event, poll_sec: float = 0.1
) -> bool:
    """Put an item on a queue, retrying while the queue is full.

    Returns:
        bool: True if the item was queued, False if stop_event was set first.
    """
    while not stop_event.is_set():
        try:
            q.put(item, timeout=poll_sec)
            return True
        except queue.Full:
            continue
    return False


def _file_reader_thread_main(
    image_path: str,
    out_queue: "queue.Queue",
    total_requests: int,
    stop_event: threading.Event,
) -> None:
    """Thread body: read an image file repeatedly and queue (frame_id, (bytes,), {}) items.

    Stops after total_requests items, when stop_event is set, or if the file cannot be read.
    """
    p = Path(image_path)
    for frame_id in range(total_requests):
        if stop_event.is_set():
            return
        try:
            data = p.read_bytes()
        except Exception as exc:
            print(
                f"[_run_one_worker] reader thread: failed to read "
                f"{image_path!r} ({exc}) -- stopping early",
                file=sys.stderr,
            )
            return
        if not _try_put_until_stopped(out_queue, (frame_id, (data,), {}), stop_event):
            return


def _queue_reader_thread_main(
    pool,
    out_queue: "queue.Queue",
    stop_event: threading.Event,
    poll_sec: float = 0.1,
) -> None:
    """Thread body: take work items from the shared-memory work queue and queue the unpacked calls locally.

    Reads each slot, releases it, unpacks the call and puts (frame_id, args, kwargs) on out_queue.
    The frame id comes from the work item, not from the packed skeleton.
    """
    while not stop_event.is_set():
        try:
            slot_id, frame_id, length = pool.work_queue.get(timeout=poll_sec)
        except queue.Empty:
            continue
        payload = pool.read_slot(slot_id, length)
        pool.release_slot(slot_id)
        _skeleton_frame_id, args, kwargs = unpack_call(payload)
        if not _try_put_until_stopped(out_queue, (frame_id, args, kwargs), stop_event):
            return


def _feeder_loop(
    stream,
    local_queue: "queue.Queue",
    dispatch_cadence: str,
    num_endpoints: int,
    max_dispatches: Optional[int],
    stop_event: Optional[threading.Event],
    reader_alive,
) -> int:
    """Drive a stream: pump completions and dispatch queued calls as capacity allows.

    Args:
        stream: A _SyncPoolStream.
        local_queue (queue.Queue): Source of (frame_id, args, kwargs) items.
        dispatch_cadence (str): 'drain' sends to whichever endpoint has room; any other value
            sends at most one call per endpoint per loop iteration, in endpoint order.
        num_endpoints (int): Number of endpoints, used by the non-drain cadence.
        max_dispatches (Optional[int]): Stop after this many dispatches (finite run).
        stop_event (Optional[threading.Event]): Run until set and the queue is empty (open-ended run).
        reader_alive: Callable reporting whether the producer is still running; in a finite run the
            loop ends early if the producer is gone and the queue is empty.

    Returns:
        int: Number of calls dispatched.

    Raises:
        ValueError: Unless exactly one of max_dispatches and stop_event is given.
    """
    if (max_dispatches is None) == (stop_event is None):
        raise ValueError("_feeder_loop: exactly one of max_dispatches/stop_event must be set")
    dispatched = 0

    def _done() -> bool:
        if max_dispatches is not None:
            return dispatched >= max_dispatches
        return stop_event.is_set() and local_queue.empty()

    while not _done():
        progressed = stream.pump()
        if dispatch_cadence == "drain":
            while stream.has_capacity() and not _done():
                try:
                    frame_id, args, kwargs = local_queue.get_nowait()
                except queue.Empty:
                    break
                stream.dispatch(*args, frame_id=frame_id, **kwargs)
                dispatched += 1
                progressed = True
        else:
            for idx in range(num_endpoints):
                if _done():
                    break
                if stream.has_capacity_at(idx):
                    try:
                        frame_id, args, kwargs = local_queue.get_nowait()
                    except queue.Empty:
                        break
                    stream.dispatch_at(idx, *args, frame_id=frame_id, **kwargs)
                    dispatched += 1
                    progressed = True
        if (
            max_dispatches is not None
            and dispatched < max_dispatches
            and not reader_alive()
            and local_queue.empty()
        ):
            break
        if not progressed:
            time.sleep(0.0005)
    return dispatched


def _run_one_worker(
    engine_cls,
    endpoints: list[str],
    concurrency: int,
    image_path: str,
    requests_per_endpoint: int,
    warmup: int,
    request_timeout_sec: Optional[float],
    dispatch_cadence: str,
    retries_per_frame: int,
    worker_id: int,
) -> WorkerResult:
    """Run one benchmark worker: send a fixed number of copies of an image and measure throughput.

    Reads image_path repeatedly in a reader thread, dispatches through an engine stream and waits
    for the responses. The first warmup * len(endpoints) responses are excluded from the
    throughput figures. Waits at most max(60 s, 0.05 s * total requests) for responses after dispatch.

    Returns:
        WorkerResult: Counts, error breakdown and throughput.

    Raises:
        FileNotFoundError: If image_path does not exist.
    """
    endpoints = list(endpoints)
    if not Path(image_path).exists():
        raise FileNotFoundError(f"image_path does not exist: {image_path!r}")
    total_requests = requests_per_endpoint * len(endpoints)

    completed = 0
    errors = 0
    client_side_errors = 0
    server_side_errors = 0
    server_side_messages: dict = {}
    warmup_remaining = warmup * len(endpoints)
    steady_start = [None]
    steady_completed = [0]

    def on_result(_frame_id, response) -> None:
        nonlocal completed, errors, warmup_remaining, client_side_errors, server_side_errors
        completed += 1
        if warmup_remaining > 0:
            warmup_remaining -= 1
        else:
            if steady_start[0] is None:
                steady_start[0] = time.perf_counter()
            steady_completed[0] += 1
        if response.HasField("status") and response.status != 0:
            errors += 1
            msg = response.status_message if response.HasField("status_message") else ""
            if msg.startswith("client-side "):
                client_side_errors += 1
            else:
                server_side_errors += 1
                if len(server_side_messages) < 5 and msg not in server_side_messages:
                    server_side_messages[msg] = 0
                if msg in server_side_messages:
                    server_side_messages[msg] += 1

    engine = engine_cls(endpoints, concurrency=concurrency)
    stream = engine.open_stream(
        on_result=on_result, ordered=False, retries_per_frame=retries_per_frame,
        request_timeout_sec=request_timeout_sec,
    )

    image_queue: "queue.Queue" = queue.Queue(maxsize=_READER_QUEUE_MAXSIZE)
    stop_reader = threading.Event()
    reader_thread = threading.Thread(
        target=_file_reader_thread_main,
        args=(image_path, image_queue, total_requests, stop_reader),
        daemon=True,
        name=f"AxIndependentWorkerReader-{worker_id}",
    )
    reader_thread.start()

    timed_out = False
    try:
        _feeder_loop(
            stream, image_queue, dispatch_cadence, len(endpoints),
            max_dispatches=total_requests, stop_event=None,
            reader_alive=reader_thread.is_alive,
        )

        deadline = time.monotonic() + max(60.0, total_requests * 0.05)
        while completed < total_requests and time.monotonic() < deadline:
            if not stream.pump():
                time.sleep(0.0005)
        if completed < total_requests:
            timed_out = True
    finally:
        stop_reader.set()
        reader_thread.join(timeout=5.0)
        if reader_thread.is_alive():
            print(
                f"[_run_one_worker] worker {worker_id}: reader thread did not "
                f"stop within 5.0s -- proceeding anyway",
                file=sys.stderr,
            )
        stream.close(timeout=30.0)
        engine.close()

    elapsed = time.perf_counter() - steady_start[0] if steady_start[0] is not None else 0.0
    throughput = steady_completed[0] / elapsed if elapsed > 0 else 0.0

    return WorkerResult(
        worker_id=worker_id,
        num_endpoints=len(endpoints),
        requests_per_endpoint=requests_per_endpoint,
        completed=completed,
        expected=total_requests,
        errors=errors,
        client_side_errors=client_side_errors,
        server_side_errors=server_side_errors,
        elapsed_sec=elapsed,
        throughput_rps=throughput,
        server_side_messages=server_side_messages,
        timed_out=timed_out,
    )


class _BatchBuffer:
    """Thread-safe buffer that sends items to a queue in batches.

    A batch is flushed when it reaches max_size items, or by flush_if_stale() once max_delay_sec has
    passed since the last flush.
    """

    def __init__(self, target_queue, max_size: int = 32, max_delay_sec: float = 0.005) -> None:
        """Create an empty buffer that flushes into target_queue."""
        self._queue = target_queue
        self._buf: list = []
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._max_size = max_size
        self._max_delay_sec = max_delay_sec

    def append(self, item) -> None:
        """Add an item, flushing the batch if it is full."""
        with self._lock:
            self._buf.append(item)
            if len(self._buf) >= self._max_size:
                self._flush_locked()

    def flush_if_stale(self) -> None:
        """Flush a non-empty batch if max_delay_sec has elapsed since the last flush."""
        with self._lock:
            if self._buf and time.monotonic() - self._last_flush >= self._max_delay_sec:
                self._flush_locked()

    def force_flush(self) -> None:
        """Flush any buffered items now."""
        with self._lock:
            if self._buf:
                self._flush_locked()

    def _flush_locked(self) -> None:
        """Put the buffered list on the target queue as one item and start a new batch; the caller holds the lock."""
        self._queue.put(self._buf)
        self._buf = []
        self._last_flush = time.monotonic()


def _node_worker_main(
    engine_cls,
    endpoints: list[str],
    concurrency: int,
    pool_name: str,
    num_slots: int,
    slot_size: int,
    free_slots,
    work_queue,
    results_queue,
    stop_event,
    retries_per_frame: int,
    retry_base_delay_sec: float,
    retry_max_delay_sec: float,
    request_timeout_sec: Optional[float],
    worker_id: int,
) -> None:
    """Entry point of a worker process spawned by _CrossProcessEngine.

    Attaches to the shared-memory pool, builds an engine and stream, and forwards calls from the work
    queue to the endpoints until stop_event is set. Responses are batched onto results_queue as
    (frame_id, response, worker_id) tuples by a flusher thread; the remaining batch is flushed on exit.
    """
    from ._shm_ring import _SlotPool

    pool = _SlotPool.attach(pool_name, num_slots, slot_size, free_slots, work_queue)
    engine = engine_cls(endpoints, concurrency=concurrency)
    out_buf = _BatchBuffer(results_queue)

    def on_result(frame_id, response) -> None:
        out_buf.append((frame_id, response, worker_id))

    stream = engine.open_stream(
        on_result=on_result,
        ordered=False,
        retries_per_frame=retries_per_frame,
        retry_base_delay_sec=retry_base_delay_sec,
        retry_max_delay_sec=retry_max_delay_sec,
        request_timeout_sec=request_timeout_sec,
    )

    local_queue: "queue.Queue" = queue.Queue(maxsize=_READER_QUEUE_MAXSIZE)
    reader_thread = threading.Thread(
        target=_queue_reader_thread_main,
        args=(pool, local_queue, stop_event),
        daemon=True,
        name=f"AxNodeWorkerReader-{worker_id}",
    )
    reader_thread.start()

    stop_flusher = threading.Event()

    def _flush_loop() -> None:
        while not stop_flusher.is_set():
            out_buf.flush_if_stale()
            time.sleep(_FLUSH_TICK_SEC)

    flusher = threading.Thread(
        target=_flush_loop, daemon=True, name=f"AxNodeWorkerFlusher-{worker_id}"
    )
    flusher.start()

    try:
        _feeder_loop(
            stream, local_queue, "drain", len(endpoints),
            max_dispatches=None, stop_event=stop_event,
            reader_alive=lambda: True,
        )
    finally:
        reader_thread.join(timeout=5.0)
        stream.close()
        stop_flusher.set()
        flusher.join(timeout=2)
        out_buf.force_flush()
        engine.close()
        pool.close()


def _worker_process_entry(
    result_queue,
    engine_cls,
    endpoints: list[str],
    concurrency: int,
    image_path: str,
    requests_per_endpoint: int,
    warmup: int,
    request_timeout_sec: Optional[float],
    dispatch_cadence: str,
    retries_per_frame: int,
    worker_id: int,
) -> None:
    """Process entry for IndependentWorkersBenchmark: run one worker, put its WorkerResult on result_queue and re-raise any exception after printing it."""
    try:
        result = _run_one_worker(
            engine_cls, endpoints, concurrency, image_path, requests_per_endpoint,
            warmup, request_timeout_sec, dispatch_cadence, retries_per_frame, worker_id,
        )
        result_queue.put(result)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise


@dataclass
class IndependentWorkersBenchmarkResult:
    """Aggregate of all benchmark worker processes.

    Attributes:
        per_worker (list): WorkerResult per worker that reported, ordered by worker id.
        num_processes (int): Processes started.
        total_endpoints (int): Endpoints each worker targeted.
        total_completed (int): Sum of completed responses.
        total_expected (int): Sum of expected responses.
        total_errors (int): Sum of errors.
        total_client_side_errors (int): Sum of client-side errors.
        total_server_side_errors (int): Sum of server-side errors.
        total_throughput_rps (float): Sum of per-worker throughput.
        any_failed (bool): True if a worker reported nothing or exited with a non-zero code.
        missing_worker_ids (list): Ids of workers that returned no result.
    """

    per_worker: list
    num_processes: int
    total_endpoints: int
    total_completed: int
    total_expected: int
    total_errors: int
    total_client_side_errors: int
    total_server_side_errors: int
    total_throughput_rps: float
    any_failed: bool
    missing_worker_ids: list


class IndependentWorkersBenchmark:
    """Benchmark that runs several independent client processes against the same endpoints.

    Each process owns its engine, replays one image file and reports its own result, so the
    processes do not share state with each other.
    """

    def __init__(
        self,
        engine_cls,
        endpoints: list[str],
        num_processes: int,
        concurrency: int,
        image_path: str,
        requests_per_endpoint: int = 1250,
        warmup: int = 30,
        request_timeout_sec: Optional[float] = 0.0,
        dispatch_cadence: str = "drain",
        retries_per_frame: int = 0,
    ) -> None:
        """Store the benchmark parameters.

        Args:
            engine_cls: Engine class each worker instantiates as engine_cls(endpoints, concurrency=...).
            endpoints (list[str]): Server addresses as 'host:port'.
            num_processes (int): Number of worker processes.
            concurrency (int): In-flight budget per worker.
            image_path (str): Image file sent in every request.
            requests_per_endpoint (int, optional): Requests per endpoint per worker. Defaults to 1250.
            warmup (int, optional): Warmup requests per endpoint excluded from throughput. Defaults to 30.
            request_timeout_sec (Optional[float], optional): Per-request gRPC deadline; 0 or None means none. Defaults to 0.0.
            dispatch_cadence (str, optional): 'drain' or per-endpoint round-robin; see _feeder_loop. Defaults to 'drain'.
            retries_per_frame (int, optional): Retry limit per request. Defaults to 0.

        Raises:
            ValueError: If endpoints is empty or num_processes is not positive.
        """
        if not endpoints:
            raise ValueError("at least one endpoint ('host:port') is required")
        if num_processes <= 0:
            raise ValueError("num_processes must be positive")
        self._engine_cls = engine_cls
        self._endpoints = list(endpoints)
        self._num_processes = num_processes
        self._concurrency = concurrency
        self._image_path = image_path
        self._requests_per_endpoint = requests_per_endpoint
        self._warmup = warmup
        self._request_timeout_sec = request_timeout_sec
        self._dispatch_cadence = dispatch_cadence
        self._retries_per_frame = retries_per_frame
        self._ctx = multiprocessing.get_context("spawn")

    def run(self, timeout: Optional[float] = None) -> IndependentWorkersBenchmarkResult:
        """Start the worker processes, collect their results and aggregate them.

        Args:
            timeout (Optional[float], optional): Seconds to wait for results; None waits until every
                worker has reported or all have exited. Defaults to None.

        Returns:
            IndependentWorkersBenchmarkResult: Per-worker and summed figures; workers that did not
            report are listed in missing_worker_ids.
        """
        result_queue = self._ctx.Queue()
        processes = []
        for i in range(self._num_processes):
            p = self._ctx.Process(
                target=_worker_process_entry,
                args=(
                    result_queue, self._engine_cls, self._endpoints, self._concurrency,
                    self._image_path, self._requests_per_endpoint, self._warmup,
                    self._request_timeout_sec, self._dispatch_cadence,
                    self._retries_per_frame, i,
                ),
                daemon=False,
                name=f"AxIndependentWorker-{i}",
            )
            p.start()
            processes.append(p)

        deadline = time.monotonic() + timeout if timeout is not None else None
        results_by_id: dict = {}
        while len(results_by_id) < self._num_processes:
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
            try:
                result = result_queue.get(timeout=remaining if remaining is not None else 1.0)
            except Exception:
                if all(not p.is_alive() for p in processes):
                    break
                continue
            results_by_id[result.worker_id] = result

        for p in processes:
            p.join(timeout=5.0)

        missing_worker_ids = sorted(set(range(self._num_processes)) - set(results_by_id.keys()))
        any_failed = bool(missing_worker_ids) or any(
            p.exitcode not in (0, None) for p in processes
        )

        per_worker = [results_by_id[i] for i in sorted(results_by_id.keys())]
        total_completed = sum(r.completed for r in per_worker)
        total_expected = sum(r.expected for r in per_worker)
        total_errors = sum(r.errors for r in per_worker)
        total_client_side_errors = sum(r.client_side_errors for r in per_worker)
        total_server_side_errors = sum(r.server_side_errors for r in per_worker)
        total_throughput_rps = sum(r.throughput_rps for r in per_worker)

        return IndependentWorkersBenchmarkResult(
            per_worker=per_worker,
            num_processes=self._num_processes,
            total_endpoints=len(self._endpoints),
            total_completed=total_completed,
            total_expected=total_expected,
            total_errors=total_errors,
            total_client_side_errors=total_client_side_errors,
            total_server_side_errors=total_server_side_errors,
            total_throughput_rps=total_throughput_rps,
            any_failed=any_failed,
            missing_worker_ids=missing_worker_ids,
        )


def format_worker_result_line(r: WorkerResult) -> str:
    """Format one worker's result as a single 'RESULT:' line."""
    return (
        f"RESULT: endpoints={r.num_endpoints} requests_per_endpoint={r.requests_per_endpoint} "
        f"aggregate_completed={r.completed}/{r.expected} aggregate_errors={r.errors} "
        f"client_side_errors={r.client_side_errors} server_side_errors={r.server_side_errors} "
        f"aggregate_throughput={r.throughput_rps:.1f}req/s balanced=True"
    )


def format_aggregate_result_line(agg: IndependentWorkersBenchmarkResult) -> str:
    """Format the aggregate result as a single 'RESULT:' line."""
    return (
        f"RESULT: num_processes={agg.num_processes} total_endpoints={agg.total_endpoints} "
        f"aggregate_completed={agg.total_completed}/{agg.total_expected} "
        f"aggregate_errors={agg.total_errors} client_side_errors={agg.total_client_side_errors} "
        f"server_side_errors={agg.total_server_side_errors} "
        f"aggregate_throughput={agg.total_throughput_rps:.1f}req/s"
    )
