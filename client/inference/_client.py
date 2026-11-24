"""Generic cross-process inference clients (blocking and asyncio).

Defines AxInferClient and AsyncAxInferClient, which hand calls to worker processes via shared memory.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Callable, Optional

from ._engine_core import (
    _DEFAULT_SHM_RING_SIZE,
    _DEFAULT_SHM_SLOT_SIZE_BYTES,
    _CrossProcessEngine,
    _PendingWaiter,
)

_DEFAULT_CONCURRENCY = 1000


class AxInferClient:
    """Blocking client that sends calls to gRPC endpoints through worker processes.

    Calls are packed into shared memory, executed by spawned worker processes that each run an
    engine of the given class, and the responses are routed back to the caller. Worker processes
    are started lazily on the first call or stream. Supports use as a context manager.

    Note:
        The first open_stream() call per client replaces any previously opened stream as the
        receiver of unmatched results; use one stream at a time.
    """

    def __init__(
        self,
        engine_cls,
        endpoints: list[str],
        concurrency: int = _DEFAULT_CONCURRENCY,
        num_workers: int = 1,
        shm_ring_size: int = _DEFAULT_SHM_RING_SIZE,
        shm_slot_size_bytes: int = _DEFAULT_SHM_SLOT_SIZE_BYTES,
    ) -> None:
        """Create the engine; no worker process is started until the first call.

        Args:
            engine_cls: Engine class instantiated in each worker as engine_cls(endpoints, concurrency=...).
            endpoints (list[str]): Server addresses as 'host:port'.
            concurrency (int, optional): Total in-flight request budget, split across workers. Defaults to 1000.
            num_workers (int, optional): Number of worker processes. Defaults to 1.
            shm_ring_size (int, optional): Number of shared-memory slots. Defaults to 64.
            shm_slot_size_bytes (int, optional): Capacity of each slot in bytes; a call whose packed
                payload is larger fails. Defaults to 1 MiB.
        """
        self._engine = _CrossProcessEngine(
            engine_cls, endpoints, concurrency, num_workers,
            shm_ring_size=shm_ring_size, shm_slot_size_bytes=shm_slot_size_bytes,
        )

    def __enter__(self) -> "AxInferClient":
        """Return the client itself."""
        return self

    def __exit__(self, *_) -> None:
        """Close the client."""
        self.close()

    @property
    def stats(self):
        """Counters of completed and failed calls (an _EngineStats), updated as results arrive."""
        return self._engine.stats

    def close(self) -> None:
        """Stop the worker processes and release the shared memory; safe to call more than once."""
        self._engine.close()

    def _infer_sync(self, *args, timeout: float = 60.0, **kwargs):
        """Submit one call and block until its response arrives.

        Args:
            *args: Positional arguments forwarded to the engine's request builder.
            timeout (float, optional): Seconds to wait for the response. Defaults to 60.0.
            **kwargs: Keyword arguments forwarded to the request builder.

        Returns:
            The response message.

        Raises:
            TimeoutError: If no response arrives within timeout.
            RuntimeError: If the response carries a non-zero status (dropped), or the engine is closed during submit.
        """
        self._engine.ensure_started(
            retries_per_frame=0, retry_base_delay_sec=0.05,
            retry_max_delay_sec=2.0, request_timeout_sec=None,
        )
        frame_id = self._engine.next_frame_id()
        fut: "concurrent.futures.Future" = concurrent.futures.Future()
        self._engine.register_waiter(frame_id, _PendingWaiter("concurrent_future", fut))
        try:
            self._engine.submit(frame_id, args, kwargs)
        except Exception:
            self._engine.unregister_waiter(frame_id)
            raise
        try:
            response = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            self._engine.unregister_waiter(frame_id)
            raise TimeoutError(
                f"infer() timed out after {timeout}s waiting for frame_id={frame_id}"
            ) from None
        if response.HasField("status") and response.status != 0:
            raise RuntimeError(f"infer() dropped: {response.status_message}")
        return response

    def open_stream(
        self,
        on_result: Callable[[int, object], None],
        ordered: bool = False,
        retries_per_frame: int = 0,
        retry_base_delay_sec: float = 0.05,
        retry_max_delay_sec: float = 2.0,
        request_timeout_sec: Optional[float] = 20.0,
    ):
        """Open a streaming session that delivers results through a callback.

        Args:
            on_result (Callable[[int, object], None]): Called as on_result(sequence, response) from a
                dispatcher thread; sequence counts pushes from 0.
            ordered (bool, optional): Deliver in push order instead of completion order. Defaults to False.
            retries_per_frame (int, optional): Retries for dropped or transiently failed calls. Defaults to 0.
            retry_base_delay_sec (float, optional): First retry delay; doubles per attempt. Defaults to 0.05.
            retry_max_delay_sec (float, optional): Upper bound on the retry delay. Defaults to 2.0.
            request_timeout_sec (Optional[float], optional): Per-request gRPC deadline; None or <= 0 means none.
                Defaults to 20.0.

        Returns:
            The stream object; call push(...) to send and close() to drain.

        Note:
            The retry and timeout settings take effect only if this call starts the workers.
        """
        return self._engine.open_stream(
            on_result, ordered=ordered, retries_per_frame=retries_per_frame,
            retry_base_delay_sec=retry_base_delay_sec, retry_max_delay_sec=retry_max_delay_sec,
            request_timeout_sec=request_timeout_sec,
        )


class AsyncAxInferClient:
    """Asyncio counterpart of AxInferClient.

    Workers, shared memory and streaming work as in the blocking client. Supports use as an async context manager.
    """

    def __init__(
        self,
        engine_cls,
        endpoints: list[str],
        concurrency: int = _DEFAULT_CONCURRENCY,
        num_workers: int = 1,
        shm_ring_size: int = _DEFAULT_SHM_RING_SIZE,
        shm_slot_size_bytes: int = _DEFAULT_SHM_SLOT_SIZE_BYTES,
    ) -> None:
        """Create the engine; see AxInferClient.__init__ for the arguments."""
        self._engine = _CrossProcessEngine(
            engine_cls, endpoints, concurrency, num_workers,
            shm_ring_size=shm_ring_size, shm_slot_size_bytes=shm_slot_size_bytes,
        )

    async def __aenter__(self) -> "AsyncAxInferClient":
        """Return the client itself."""
        return self

    async def __aexit__(self, *_) -> None:
        """Close the client."""
        self.close()

    @property
    def stats(self):
        """Counters of completed and failed calls (an _EngineStats), updated as results arrive."""
        return self._engine.stats

    def close(self) -> None:
        """Stop the worker processes and release the shared memory; safe to call more than once. Blocking."""
        self._engine.close()

    async def _infer_async(self, *args, timeout: float = 60.0, **kwargs):
        """Submit one call and await its response.

        Args:
            *args: Positional arguments forwarded to the engine's request builder.
            timeout (float, optional): Seconds to wait for the response. Defaults to 60.0.
            **kwargs: Keyword arguments forwarded to the request builder.

        Returns:
            The response message.

        Raises:
            TimeoutError: If no response arrives within timeout.
            RuntimeError: If the response carries a non-zero status (dropped), or the engine is closed during submit.
            asyncio.CancelledError: Re-raised after the pending call is unregistered.
        """
        loop = asyncio.get_running_loop()
        self._engine.ensure_started(
            retries_per_frame=0, retry_base_delay_sec=0.05,
            retry_max_delay_sec=2.0, request_timeout_sec=None,
        )
        frame_id = self._engine.next_frame_id()
        fut: "asyncio.Future" = loop.create_future()
        self._engine.register_waiter(frame_id, _PendingWaiter("asyncio_future", fut, loop=loop))
        try:
            await loop.run_in_executor(None, self._engine.submit, frame_id, args, kwargs)
        except Exception:
            self._engine.unregister_waiter(frame_id)
            raise
        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.CancelledError:
            fut.cancel()
            self._engine.unregister_waiter(frame_id)
            raise
        except asyncio.TimeoutError:
            self._engine.unregister_waiter(frame_id)
            raise TimeoutError(
                f"infer() timed out after {timeout}s waiting for frame_id={frame_id}"
            ) from None
        if response.HasField("status") and response.status != 0:
            raise RuntimeError(f"infer() dropped: {response.status_message}")
        return response

    def open_stream(
        self,
        on_result: Callable[[int, object], None],
        ordered: bool = False,
        retries_per_frame: int = 0,
        retry_base_delay_sec: float = 0.05,
        retry_max_delay_sec: float = 2.0,
        request_timeout_sec: Optional[float] = 20.0,
    ):
        """Open a streaming session; same arguments and behaviour as AxInferClient.open_stream."""
        return self._engine.open_stream(
            on_result, ordered=ordered, retries_per_frame=retries_per_frame,
            retry_base_delay_sec=retry_base_delay_sec, retry_max_delay_sec=retry_max_delay_sec,
            request_timeout_sec=request_timeout_sec,
        )
