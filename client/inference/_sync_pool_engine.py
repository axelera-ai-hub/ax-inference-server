"""gRPC engine that issues non-blocking calls over a pool of endpoints.

Defines _SyncPoolEngine (base class holding channels and stubs) and _SyncPoolStream (windowed
dispatch, retry with backoff and completion polling). Used by the worker processes.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, Optional

import grpc

from axinfer.v1 import inference_pb2

_DROPPED = inference_pb2.InferenceStatus.DROPPED

_TRANSIENT_GRPC_CODES = frozenset({
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.UNAVAILABLE,
})

_POLL_IDLE_SLEEP_SEC = 0.0005


class _EndpointState:
    """In-flight bookkeeping for one endpoint.

    Attributes:
        pending (dict): Maps each outstanding gRPC future to (frame_id, args, kwargs, attempt, start_time).
    """

    def __init__(self) -> None:
        self.pending: dict = {}


class _SyncPoolEngine:
    """Base class for engines that talk to a pool of gRPC endpoints with non-blocking calls.

    Opens one insecure channel and one stub per endpoint. Subclasses supply the stubs, the request
    message and the 'dropped' response message. Work is issued through a _SyncPoolStream.

    Attributes:
        _per_endpoint_window (int): Maximum outstanding requests per endpoint, derived from the
            concurrency budget divided across endpoints (at least 1; 0 if concurrency is 0 or negative).
    """

    def __init__(self, endpoints: list[str], concurrency: int) -> None:
        """Open a channel and stub for each endpoint.

        Args:
            endpoints (list[str]): Server addresses as 'host:port'.
            concurrency (int): Total in-flight budget across all endpoints.

        Raises:
            ValueError: If endpoints is empty.
        """
        if not endpoints:
            raise ValueError("at least one endpoint ('host:port') is required")
        self._endpoints = endpoints
        self._concurrency = concurrency
        self._per_endpoint_window = (
            max(1, concurrency // len(endpoints)) if concurrency > 0 else 0
        )
        self._channels = [grpc.insecure_channel(ep) for ep in endpoints]
        self._stubs = self._build_stubs(endpoints, self._channels)

    def _build_stubs(self, endpoints: list[str], channels: list) -> list:
        """Create one gRPC stub per channel; implemented by subclasses."""
        raise NotImplementedError

    def _make_request(self, *args, request_id: Optional[str] = None, **kwargs):
        """Build the request message for one call; implemented by subclasses."""
        raise NotImplementedError

    def _make_dropped_response(self, status_message: str):
        """Build a response message with DROPPED status carrying status_message; implemented by subclasses."""
        raise NotImplementedError

    def close(self) -> None:
        """Close all gRPC channels."""
        for ch in self._channels:
            ch.close()

    def open_stream(
        self,
        on_result: Callable[[int, object], None],
        ordered: bool = False,
        retries_per_frame: int = 0,
        retry_base_delay_sec: float = 0.05,
        retry_max_delay_sec: float = 2.0,
        request_timeout_sec: Optional[float] = 20.0,
        trace_recorder=None,
    ) -> "_SyncPoolStream":
        """Create a stream for issuing calls on this engine.

        Args:
            on_result (Callable[[int, object], None]): Called as on_result(frame_id, response) for each finished call.
            ordered (bool, optional): Accepted for interface compatibility; not used by this engine. Defaults to False.
            retries_per_frame (int, optional): Retries for dropped or transiently failed calls; a negative value retries
                without limit. Defaults to 0.
            retry_base_delay_sec (float, optional): First retry delay; doubles per attempt. Defaults to 0.05.
            retry_max_delay_sec (float, optional): Upper bound on the retry delay. Defaults to 2.0.
            request_timeout_sec (Optional[float], optional): Per-request gRPC deadline; None or <= 0 means none. Defaults to 20.0.
            trace_recorder (optional): Object with record(tag, frame_id, attempt, timestamp), called when a request is sent.
                Defaults to None.

        Returns:
            _SyncPoolStream: The new stream.
        """
        return _SyncPoolStream(
            engine=self,
            on_result=on_result,
            retries_per_frame=retries_per_frame,
            retry_base_delay_sec=retry_base_delay_sec,
            retry_max_delay_sec=retry_max_delay_sec,
            request_timeout_sec=request_timeout_sec,
            trace_recorder=trace_recorder,
        )


class _SyncPoolStream:
    """Single-threaded dispatcher over a _SyncPoolEngine's endpoints.

    The owner repeatedly calls pump() to complete finished requests and send due retries, and calls
    dispatch() or dispatch_at() while there is capacity. Completed calls, including client-side failures
    converted to dropped responses, are reported through the on_result callback.

    Note:
        Not thread-safe; all methods must be called from one thread.
    """

    def __init__(
        self,
        engine: _SyncPoolEngine,
        on_result: Callable[[int, object], None],
        retries_per_frame: int,
        retry_base_delay_sec: float,
        retry_max_delay_sec: float,
        request_timeout_sec: Optional[float],
        trace_recorder=None,
    ) -> None:
        """Store the settings and create empty per-endpoint state; use _SyncPoolEngine.open_stream instead of calling this directly."""
        self._engine = engine
        self._on_result = on_result
        self._retries_per_frame = retries_per_frame
        self._retry_base_delay_sec = retry_base_delay_sec
        self._retry_max_delay_sec = retry_max_delay_sec
        self._request_timeout_sec = (
            request_timeout_sec if request_timeout_sec and request_timeout_sec > 0 else None
        )
        self._trace_recorder = trace_recorder

        self._states = [_EndpointState() for _ in range(len(engine._stubs))]

        self._retry_queue: list = []

    def _total_pending(self) -> int:
        """Return the number of requests currently outstanding across all endpoints."""
        return sum(len(s.pending) for s in self._states)

    def has_capacity(self) -> bool:
        """Return True if at least one endpoint has fewer outstanding requests than its window."""
        window = self._engine._per_endpoint_window
        return any(len(s.pending) < window for s in self._states)

    def dispatch(self, *args, frame_id: Optional[int] = None, **kwargs) -> None:
        """Send a call to the least-loaded endpoint that has room.

        Args:
            *args: Positional arguments for the engine's request builder.
            frame_id (Optional[int], optional): Id reported to on_result and used in the default request id.
            **kwargs: Keyword arguments for the request builder; a 'request_id' overrides the generated one.

        Raises:
            RuntimeError: If no endpoint has capacity; check has_capacity() first.
        """
        idx = self._pick_least_loaded_endpoint()
        if idx is None:
            raise RuntimeError(
                "dispatch() called without confirming has_capacity() first "
                f"(no endpoint has room under per_endpoint_window="
                f"{self._engine._per_endpoint_window})"
            )
        self._send(idx, frame_id, args, kwargs, attempt=0)

    def has_capacity_at(self, idx: int) -> bool:
        """Return True if endpoint idx has fewer outstanding requests than its window."""
        return len(self._states[idx].pending) < self._engine._per_endpoint_window

    def dispatch_at(self, idx: int, *args, frame_id: Optional[int] = None, **kwargs) -> None:
        """Send a call to a specific endpoint.

        Args:
            idx (int): Index into the engine's endpoint list.
            *args: Positional arguments for the engine's request builder.
            frame_id (Optional[int], optional): Id reported to on_result.
            **kwargs: Keyword arguments for the request builder.

        Raises:
            RuntimeError: If endpoint idx is at its window; check has_capacity_at(idx) first.
        """
        if not self.has_capacity_at(idx):
            raise RuntimeError(
                f"dispatch_at({idx}) called without confirming "
                f"has_capacity_at({idx}) first (endpoint already at its "
                f"per_endpoint_window={self._engine._per_endpoint_window})"
            )
        self._send(idx, frame_id, args, kwargs, attempt=0)

    def _pick_least_loaded_endpoint(self) -> Optional[int]:
        """Return the index of the endpoint with the fewest outstanding requests below its window, or None if all are full."""
        window = self._engine._per_endpoint_window
        candidates = [i for i, s in enumerate(self._states) if len(s.pending) < window]
        if not candidates:
            return None
        return min(candidates, key=lambda i: len(self._states[i].pending))

    def _send(self, idx: int, frame_id, args: tuple, kwargs: dict, attempt: int) -> None:
        """Issue one request asynchronously and record it as pending.

        The request id is the caller's 'request_id' kwarg if given, otherwise '<frame_id>-a<attempt>'.
        """
        state = self._states[idx]
        call_kwargs = dict(kwargs)
        caller_request_id = call_kwargs.pop("request_id", None)
        request_id = caller_request_id if caller_request_id is not None else f"{frame_id}-a{attempt}"
        req = self._engine._make_request(*args, request_id=request_id, **call_kwargs)
        t_start = time.monotonic()
        fut = self._engine._stubs[idx].Infer.future(req, timeout=self._request_timeout_sec)
        state.pending[fut] = (frame_id, args, kwargs, attempt, t_start)
        if self._trace_recorder is not None:
            self._trace_recorder.record("t2", frame_id, attempt, t_start)

    def pump(self) -> bool:
        """Send retries that are due and process finished requests.

        Returns:
            bool: True if any retry was sent or any request completed.
        """
        progressed = False

        now = time.monotonic()
        due = [r for r in self._retry_queue if r[0] <= now]
        if due:
            self._retry_queue = [r for r in self._retry_queue if r[0] > now]
        for _retry_at, idx, frame_id, args, kwargs, attempt in due:
            progressed = True
            self._send(idx, frame_id, args, kwargs, attempt)

        for idx, state in enumerate(self._states):
            done_futs = [f for f in state.pending if f.done()]
            for fut in done_futs:
                item = state.pending.pop(fut, None)
                if item is None:
                    continue
                progressed = True
                frame_id, args, kwargs, attempt, _t_start = item
                self._handle_completion(idx, fut, frame_id, args, kwargs, attempt)

        return progressed

    def _handle_completion(self, idx: int, fut, frame_id, args: tuple, kwargs: dict, attempt: int) -> None:
        """Turn a finished future into a result, a scheduled retry, or a dropped response.

        DEADLINE_EXCEEDED and UNAVAILABLE errors and server responses with DROPPED status are retried
        with exponential backoff while attempts remain; once retries run out the last response is
        reported. Other gRPC errors and unexpected exceptions are reported immediately as dropped
        responses with a 'client-side' message.
        """
        dropped = False
        try:
            result = fut.result()
            dropped = result.HasField("status") and result.status == _DROPPED
        except grpc.RpcError as exc:
            code = exc.code()
            if code not in _TRANSIENT_GRPC_CODES:
                result = self._engine._make_dropped_response(
                    f"client-side non-transient error {code.name}: {exc.details()}"
                )
                self._on_result(frame_id, result)
                return
            result = self._engine._make_dropped_response(
                f"client-side {code.name} after {self._request_timeout_sec}s (attempt {attempt})"
            )
            dropped = True
        except Exception as exc:
            result = self._engine._make_dropped_response(f"client-side error: {exc}")
            self._on_result(frame_id, result)
            return

        if dropped and (self._retries_per_frame < 0 or attempt < self._retries_per_frame):
            backoff = min(
                self._retry_base_delay_sec * (2 ** attempt), self._retry_max_delay_sec
            )
            self._retry_queue.append(
                (time.monotonic() + backoff, idx, frame_id, args, kwargs, attempt + 1)
            )
            return

        self._on_result(frame_id, result)

    def _still_draining(self) -> bool:
        """Return True while requests are outstanding or retries are waiting."""
        return self._total_pending() > 0 or bool(self._retry_queue)

    def close(self, timeout: float = 60.0) -> None:
        """Pump until all outstanding requests and retries finish.

        Args:
            timeout (float, optional): Maximum seconds to wait. Defaults to 60.0. If work remains a warning is
                printed to stderr and the method returns anyway.
        """
        deadline = time.monotonic() + timeout
        while self._still_draining() and time.monotonic() < deadline:
            if not self.pump():
                time.sleep(_POLL_IDLE_SLEEP_SEC)
        if self._still_draining():
            print(
                f"[_SyncPoolStream] close(): {self._total_pending()} call(s) still in "
                f"flight ({len(self._retry_queue)} awaiting retry) after {timeout}s -- "
                "returning anyway",
                file=sys.stderr,
            )
