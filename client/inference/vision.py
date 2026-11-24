"""Vision clients for the AxInference gRPC service.

Exposes AxVisionClient and AsyncAxVisionClient; each wraps the generic cross-process client
with a gRPC engine that sends InferRequest messages.
"""
from __future__ import annotations

from typing import Optional

from axinfer.v1 import inference_pb2, inference_pb2_grpc

from ._client import _DEFAULT_CONCURRENCY, AsyncAxInferClient, AxInferClient
from ._engine_core import _DEFAULT_SHM_RING_SIZE, _DEFAULT_SHM_SLOT_SIZE_BYTES
from ._sync_pool_engine import _SyncPoolEngine


class _SyncPoolVisionEngine(_SyncPoolEngine):
    """Pooled gRPC engine for the AxInference vision service (image in, FrameResult out)."""

    def _build_stubs(self, endpoints: list[str], channels: list) -> list:
        """Create one AxInferenceStub per channel."""
        return [inference_pb2_grpc.AxInferenceStub(ch) for ch in channels]

    def _make_request(self, image_bytes: bytes, request_id: Optional[str] = None):
        """Build an InferRequest carrying the encoded image."""
        return inference_pb2.InferRequest(image_data=image_bytes, request_id=request_id)

    def _make_dropped_response(self, status_message: str):
        """Build a FrameResult with status DROPPED for a call that failed on the client side."""
        return inference_pb2.FrameResult(
            status=inference_pb2.InferenceStatus.DROPPED,
            status_message=status_message,
        )


class AxVisionClient(AxInferClient):
    """Blocking client for the vision inference gRPC service.

    Sends encoded images to one or more endpoints and returns FrameResult messages.
    """

    def __init__(
        self,
        endpoints: list[str],
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
        num_workers: int = 1,
        shm_ring_size: int = _DEFAULT_SHM_RING_SIZE,
        shm_slot_size_bytes: int = _DEFAULT_SHM_SLOT_SIZE_BYTES,
    ) -> None:
        """Create the client.

        Args:
            endpoints (list[str]): Server addresses as 'host:port'.
            concurrency (int, optional): Total in-flight request budget. Defaults to 1000.
            num_workers (int, optional): Number of worker processes. Defaults to 1.
            shm_ring_size (int, optional): Number of shared-memory slots. Defaults to 64.
            shm_slot_size_bytes (int, optional): Capacity of each slot in bytes; must hold one encoded image. Defaults to 1 MiB.
        """
        super().__init__(
            _SyncPoolVisionEngine, endpoints, concurrency=concurrency, num_workers=num_workers,
            shm_ring_size=shm_ring_size, shm_slot_size_bytes=shm_slot_size_bytes,
        )

    def infer(self, image_bytes: bytes, request_id: Optional[str] = None, timeout: float = 60.0):
        """Run inference on one encoded image and wait for the result.

        Args:
            image_bytes (bytes): Encoded image data (e.g. JPEG).
            request_id (Optional[str], optional): Id echoed with the request; generated per attempt if None.
            timeout (float, optional): Seconds to wait. Defaults to 60.0.

        Returns:
            FrameResult: The server's response.

        Raises:
            TimeoutError: If no response arrives within timeout.
            RuntimeError: If the call was dropped or failed.
        """
        return self._infer_sync(image_bytes, request_id=request_id, timeout=timeout)


class AsyncAxVisionClient(AsyncAxInferClient):
    """Asyncio client for the vision inference gRPC service; see AxVisionClient."""

    def __init__(
        self,
        endpoints: list[str],
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
        num_workers: int = 1,
        shm_ring_size: int = _DEFAULT_SHM_RING_SIZE,
        shm_slot_size_bytes: int = _DEFAULT_SHM_SLOT_SIZE_BYTES,
    ) -> None:
        """Create the client; see AxVisionClient.__init__ for the arguments."""
        super().__init__(
            _SyncPoolVisionEngine, endpoints, concurrency=concurrency, num_workers=num_workers,
            shm_ring_size=shm_ring_size, shm_slot_size_bytes=shm_slot_size_bytes,
        )

    async def infer(
        self, image_bytes: bytes, request_id: Optional[str] = None, timeout: float = 60.0
    ):
        """Run inference on one encoded image and await the result.

        Args:
            image_bytes (bytes): Encoded image data (e.g. JPEG).
            request_id (Optional[str], optional): Id echoed with the request; generated per attempt if None.
            timeout (float, optional): Seconds to wait. Defaults to 60.0.

        Returns:
            FrameResult: The server's response.

        Raises:
            TimeoutError: If no response arrives within timeout.
            RuntimeError: If the call was dropped or failed.
        """
        return await self._infer_async(image_bytes, request_id=request_id, timeout=timeout)
