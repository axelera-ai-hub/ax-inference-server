"""Cross-process engine core for the inference clients.

Provides the engine that dispatches calls to worker processes over shared memory and the
callback stream used for pipelined submission. Private to the inference package.
"""
from __future__ import annotations

import heapq
import multiprocessing
import queue
import sys
import threading
import time
import uuid
from typing import Callable, Optional

from ._independent_workers import _node_worker_main
from ._shm_ring import _SlotPool, pack_call

_DEFAULT_SHM_RING_SIZE = 64
_DEFAULT_SHM_SLOT_SIZE_BYTES = 1024 * 1024

_DEFAULT_WORK_QUEUE_MAXSIZE = 256

_SUBMIT_POLL_TIMEOUT_SEC = 0.5


class _PendingWaiter:
    """A registered caller waiting for the response to one frame id.

    Attributes:
        kind (str): 'concurrent_future' (resolved directly) or 'asyncio_future' (resolved on its event loop).
        fut: The future to resolve with the response.
        loop: The event loop owning fut; required for 'asyncio_future', otherwise None.
    """

    __slots__ = ("kind", "fut", "loop")

    def __init__(self, kind: str, fut, loop=None) -> None:
        """Store the waiter.

        Raises:
            ValueError: If kind is unknown or an asyncio_future waiter has no loop.
        """
        if kind not in ("concurrent_future", "asyncio_future"):
            raise ValueError(f"unknown _PendingWaiter kind: {kind!r}")
        if kind == "asyncio_future" and loop is None:
            raise ValueError("asyncio_future waiter requires loop")
        self.kind = kind
        self.fut = fut
        self.loop = loop


def _resolve_asyncio_future(fut, response) -> None:
    """Set the response on an asyncio future unless it is already done (e.g. cancelled). Runs on the future's loop."""
    if not fut.done():
        fut.set_result(response)


class _EngineStats:
    """Running totals of results received by an engine.

    Attributes:
        total_count (int): Responses received.
        failed_count (int): Responses with a non-zero status.
    """

    def __init__(self) -> None:
        """Start both counters at zero."""
        self.total_count = 0
        self.failed_count = 0


class _CrossProcessEngine:
    """Fan-out engine that runs calls in spawned worker processes.

    Callers pack a call into a free shared-memory slot and put (slot, frame_id, length) on a work
    queue. Each worker process (see _node_worker_main) takes items from the queue, issues the
    request through its own engine_cls instance and puts batches of (frame_id, response, worker_id)
    on a results queue. A dispatcher thread in this process reads that queue and resolves the
    waiter registered for the frame id, or forwards to the active stream.

    Note:
        Workers are started lazily by ensure_started(). Frame ids are unique per engine. Only the
        most recently opened stream receives results that have no registered waiter.
    """

    def __init__(
        self,
        engine_cls,
        endpoints: list[str],
        concurrency: int,
        num_workers: int,
        shm_ring_size: int = _DEFAULT_SHM_RING_SIZE,
        shm_slot_size_bytes: int = _DEFAULT_SHM_SLOT_SIZE_BYTES,
        work_queue_maxsize: int = _DEFAULT_WORK_QUEUE_MAXSIZE,
    ) -> None:
        """Allocate the shared-memory pool and queues; no process is started yet.

        Args:
            engine_cls: Engine class each worker instantiates as engine_cls(endpoints, concurrency=...).
            endpoints (list[str]): Server addresses as 'host:port'.
            concurrency (int): Total in-flight budget; split across workers as evenly as possible
                (the first concurrency % num_workers workers get one extra).
            num_workers (int): Number of worker processes.
            shm_ring_size (int, optional): Number of shared-memory slots. Defaults to 64.
            shm_slot_size_bytes (int, optional): Size of each slot in bytes. Defaults to 1 MiB.
            work_queue_maxsize (int, optional): Capacity of the work queue. Defaults to 256.

        Raises:
            ValueError: If num_workers is not positive.
        """
        if num_workers <= 0:
            raise ValueError("num_workers must be positive")
        self._engine_cls = engine_cls
        self._endpoints = list(endpoints)
        self._num_workers = num_workers

        base = concurrency // num_workers
        remainder = concurrency % num_workers
        self._per_worker_caps = [base + (1 if i < remainder else 0) for i in range(num_workers)]

        self._ctx = multiprocessing.get_context("spawn")
        self._results_queue = self._ctx.Queue()
        self._stop_event = self._ctx.Event()

        unique = uuid.uuid4().hex[:8]
        self._pool = _SlotPool.create(
            self._ctx, f"axinferpool_{unique}", shm_ring_size, shm_slot_size_bytes,
            work_queue_maxsize=work_queue_maxsize,
        )

        self._processes: list = []
        self._started = False
        self._closed = False

        self._frame_counter = 0
        self._counter_lock = threading.Lock()

        self._pending: dict[int, _PendingWaiter] = {}
        self._pending_lock = threading.Lock()
        self._active_stream: Optional["_CrossProcessInferenceStream"] = None

        self._dispatcher_thread: Optional[threading.Thread] = None
        self._stop_dispatcher = threading.Event()

        self._stats = _EngineStats()

    @property
    def stats(self) -> _EngineStats:
        """Counters of responses received; updated by the dispatcher thread."""
        return self._stats

    def ensure_started(
        self,
        retries_per_frame: int,
        retry_base_delay_sec: float,
        retry_max_delay_sec: float,
        request_timeout_sec: Optional[float],
    ) -> None:
        """Start the worker processes and the dispatcher thread if not already running.

        Args:
            retries_per_frame (int): Retry limit passed to each worker's stream.
            retry_base_delay_sec (float): First retry delay.
            retry_max_delay_sec (float): Upper bound on the retry delay.
            request_timeout_sec (Optional[float]): Per-request gRPC deadline.

        Note:
            The settings apply only on the first call; later calls return immediately.
        """
        if self._started:
            return
        for i in range(self._num_workers):
            p = self._ctx.Process(
                target=_node_worker_main,
                args=(
                    self._engine_cls, self._endpoints, self._per_worker_caps[i],
                    self._pool.name, self._pool.num_slots, self._pool.slot_size,
                    self._pool.free_slots, self._pool.work_queue,
                    self._results_queue, self._stop_event,
                    retries_per_frame, retry_base_delay_sec, retry_max_delay_sec,
                    request_timeout_sec, i,
                ),
                daemon=True,
                name=f"AxInferNodeWorker-{i}",
            )
            p.start()
            self._processes.append(p)

        self._dispatcher_thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="AxInferEngineDispatcher"
        )
        self._dispatcher_thread.start()
        self._started = True

    def close(self) -> None:
        """Stop the workers and dispatcher and free the shared memory; idempotent.

        Signals workers to stop, waits up to 15 s in total for them to exit and terminates any that
        remain, then joins the dispatcher thread (up to 5 s) and unlinks the shared-memory block.
        """
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._stop_event.set()
            deadline = time.monotonic() + 15
            for p in self._processes:
                p.join(timeout=max(0.0, deadline - time.monotonic()))
                if p.is_alive():
                    p.terminate()
            self._stop_dispatcher.set()
            if self._dispatcher_thread is not None:
                self._dispatcher_thread.join(timeout=5)
        self._pool.close()
        self._pool.unlink()

    def _dispatch_loop(self) -> None:
        """Dispatcher thread body: read result batches, update stats and route each result until stopped."""
        while not self._stop_dispatcher.is_set():
            try:
                batch = self._results_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            for frame_id, response, _worker_id in batch:
                self._stats.total_count += 1
                if response.HasField("status") and response.status != 0:
                    self._stats.failed_count += 1
                self._route_result(frame_id, response)

    def _route_result(self, frame_id: int, response) -> None:
        """Deliver a response to the waiter registered for frame_id, else to the active stream.

        Results with neither a waiter nor an active stream are discarded.
        """
        with self._pending_lock:
            waiter = self._pending.pop(frame_id, None)
            stream = self._active_stream
        if waiter is not None:
            if waiter.kind == "concurrent_future":
                if not waiter.fut.cancelled():
                    waiter.fut.set_result(response)
            else:
                waiter.loop.call_soon_threadsafe(_resolve_asyncio_future, waiter.fut, response)
            return
        if stream is not None:
            stream._deliver(frame_id, response)

    def next_frame_id(self) -> int:
        """Return the next unused frame id (thread-safe)."""
        with self._counter_lock:
            frame_id = self._frame_counter
            self._frame_counter += 1
            return frame_id

    def register_waiter(self, frame_id: int, waiter: _PendingWaiter) -> None:
        """Register a waiter to be resolved when frame_id's response arrives."""
        with self._pending_lock:
            self._pending[frame_id] = waiter

    def unregister_waiter(self, frame_id: int) -> None:
        """Remove the waiter for frame_id if present."""
        with self._pending_lock:
            self._pending.pop(frame_id, None)

    def submit(self, frame_id: int, args: tuple, kwargs: dict) -> None:
        """Pack a call into shared memory and queue it for a worker.

        Blocks while no slot is free or the work queue is full. The slot is released again if
        writing or queueing fails.

        Args:
            frame_id (int): Id the response will be tagged with.
            args (tuple): Positional call arguments; only bytes, str, numbers, bool, None and
                tuples/lists/dicts of those are supported.
            kwargs (dict): Keyword call arguments, same restriction.

        Raises:
            RuntimeError: If the engine is closed while waiting.
            ValueError: If the packed payload exceeds the slot size.
            TypeError: If an argument has an unsupported type.
        """
        payload = pack_call(args, kwargs, frame_id)
        slot_id = None
        try:
            slot_id = self._blocking_acquire_slot(len(payload))
            self._pool.write_slot(slot_id, payload)
            self._blocking_put_work(slot_id, frame_id, len(payload))
        except Exception:
            if slot_id is not None:
                self._pool.release_slot(slot_id)
            raise

    def _blocking_acquire_slot(self, payload_len: int) -> int:
        """Wait for a free slot, polling so a close can interrupt the wait.

        Raises:
            RuntimeError: If the engine is closed while waiting.
            ValueError: If payload_len exceeds the slot size.
        """
        while True:
            if self._closed or self._stop_event.is_set():
                raise RuntimeError(
                    "engine closed while a call was blocked waiting for a "
                    "free shared-memory slot -- submit was abandoned"
                )
            try:
                return self._pool.acquire_slot(payload_len, timeout=_SUBMIT_POLL_TIMEOUT_SEC)
            except queue.Empty:
                continue

    def _blocking_put_work(self, slot_id: int, frame_id: int, length: int) -> None:
        """Put a work item on the work queue, polling so a close can interrupt the wait.

        Raises:
            RuntimeError: If the engine is closed while waiting.
        """
        item = (slot_id, frame_id, length)
        while True:
            if self._closed or self._stop_event.is_set():
                raise RuntimeError(
                    "engine closed while a call was blocked waiting for "
                    "work_queue capacity -- submit was abandoned"
                )
            try:
                self._pool.work_queue.put(item, timeout=_SUBMIT_POLL_TIMEOUT_SEC)
                return
            except queue.Full:
                continue

    def open_stream(
        self,
        on_result: Callable[[int, object], None],
        ordered: bool = False,
        retries_per_frame: int = 0,
        retry_base_delay_sec: float = 0.05,
        retry_max_delay_sec: float = 2.0,
        request_timeout_sec: Optional[float] = 20.0,
    ) -> "_CrossProcessInferenceStream":
        """Start the workers if needed and open a callback-based stream.

        Args:
            on_result (Callable[[int, object], None]): Called as on_result(sequence, response) from the dispatcher thread.
            ordered (bool, optional): Deliver in push order. Defaults to False.
            retries_per_frame (int, optional): Retry limit. Defaults to 0.
            retry_base_delay_sec (float, optional): First retry delay. Defaults to 0.05.
            retry_max_delay_sec (float, optional): Retry delay cap. Defaults to 2.0.
            request_timeout_sec (Optional[float], optional): Per-request gRPC deadline. Defaults to 20.0.

        Returns:
            _CrossProcessInferenceStream: The new stream, now the engine's active stream.
        """
        self.ensure_started(
            retries_per_frame, retry_base_delay_sec, retry_max_delay_sec, request_timeout_sec
        )
        stream = _CrossProcessInferenceStream(self, on_result=on_result, ordered=ordered)
        with self._pending_lock:
            self._active_stream = stream
        return stream


class _CrossProcessInferenceStream:
    """Push-style handle for streaming calls through a _CrossProcessEngine.

    Maps engine-wide frame ids to per-stream sequence numbers (starting at 0), delivers responses to
    a callback either as they complete or in push order, and tracks the number of calls in flight so
    close() can drain them.

    Note:
        The callback runs on the engine's dispatcher thread, and in ordered mode ordering state is
        touched only from that thread.
    """

    def __init__(self, engine: _CrossProcessEngine, on_result, ordered: bool) -> None:
        """Create the stream; use _CrossProcessEngine.open_stream instead of calling this directly."""
        self._engine = engine
        self._on_result = on_result
        self._ordered = ordered
        self._heap: list[tuple[int, object]] = []
        self._next_deliver = 0

        self._local_seq = 0
        self._global_to_local: dict[int, int] = {}
        self._map_lock = threading.Lock()

        self._inflight = 0
        self._lock = threading.Lock()
        self._drained = threading.Condition(self._lock)

    def __enter__(self) -> "_CrossProcessInferenceStream":
        """Return the stream itself."""
        return self

    def __exit__(self, *_) -> None:
        """Close the stream, waiting for in-flight calls."""
        self.close()

    def push(self, *args, **kwargs) -> None:
        """Submit one call; its response is delivered to the callback with the call's sequence number.

        Blocks if the engine has no free slot or work-queue capacity. Arguments are as for _CrossProcessEngine.submit.
        """
        with self._map_lock:
            local_seq = self._local_seq
            self._local_seq += 1
        global_frame_id = self._engine.next_frame_id()
        with self._map_lock:
            self._global_to_local[global_frame_id] = local_seq
        with self._lock:
            self._inflight += 1
        self._engine.submit(global_frame_id, args, kwargs)

    def close(self, timeout: float = 60.0) -> None:
        """Wait for all in-flight calls to complete, then detach from the engine.

        Args:
            timeout (float, optional): Maximum seconds to wait. Defaults to 60.0. If calls are still
                pending afterwards a warning is printed to stderr and the method returns anyway.
        """
        with self._lock:
            drained = self._drained.wait_for(lambda: self._inflight == 0, timeout=timeout)
        if not drained:
            print(
                f"[_CrossProcessInferenceStream] close(): {self._inflight} call(s) "
                f"still in flight after {timeout}s -- returning anyway",
                file=sys.stderr,
            )
        with self._engine._pending_lock:
            if self._engine._active_stream is self:
                self._engine._active_stream = None

    def _deliver(self, global_frame_id: int, response) -> None:
        """Handle a response routed from the engine.

        Unknown frame ids are ignored. In ordered mode a response is held until all earlier sequence
        numbers have been delivered.
        """
        with self._map_lock:
            local_seq = self._global_to_local.pop(global_frame_id, None)
        if local_seq is None:
            return
        if not self._ordered:
            self._on_result(local_seq, response)
        else:
            heapq.heappush(self._heap, (local_seq, response))
            while self._heap and self._heap[0][0] == self._next_deliver:
                _, resp = heapq.heappop(self._heap)
                self._on_result(self._next_deliver, resp)
                self._next_deliver += 1
        with self._lock:
            self._inflight -= 1
            if self._inflight == 0:
                self._drained.notify_all()
