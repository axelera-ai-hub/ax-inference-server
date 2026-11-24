"""Shared-memory transport used to hand calls from the client process to worker processes.

Provides pack_call/unpack_call for serialising a call, the _SlotPool slot allocator used by the
engine, and an unused ring-buffer variant (_WorkerChannel).
"""
from __future__ import annotations

import ctypes
import pickle
import struct
import time
from multiprocessing import shared_memory
from typing import Optional

_LEN_STRUCT = struct.Struct("<Q")
_POLL_BACKOFF_SEC = 0.0005


class _BytesRef:
    """Placeholder left in a pickled call skeleton where a bytes value was moved out.

    Attributes:
        offset (int): Start of the bytes within the concatenated blob.
        length (int): Number of bytes.
    """

    __slots__ = ("offset", "length")

    def __init__(self, offset: int, length: int) -> None:
        self.offset = offset
        self.length = length


def _extract_bytes(value, collected: list):
    """Copy a call structure, replacing each bytes value with a _BytesRef and appending the bytes to collected.

    Recurses through tuples, lists and dicts. This keeps large payloads out of the pickle.

    Raises:
        TypeError: For any type other than bytes, tuple, list, dict, str, int, float, bool or None.
    """
    if isinstance(value, bytes):
        offset = sum(len(b) for b in collected)
        collected.append(value)
        return _BytesRef(offset, len(value))
    if isinstance(value, tuple):
        return tuple(_extract_bytes(v, collected) for v in value)
    if isinstance(value, list):
        return [_extract_bytes(v, collected) for v in value]
    if isinstance(value, dict):
        return {k: _extract_bytes(v, collected) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise TypeError(
        f"_shm_ring: don't know how to scan a value of type {type(value).__name__} "
        "for embedded bytes payloads -- only bytes/tuple/list/dict/str/int/float/bool/None "
        "are handled; extend _extract_bytes explicitly for a new call shape rather than "
        "adding a silent pass-through"
    )


def _reinject_bytes(value, blob: bytes):
    """Inverse of _extract_bytes: replace each _BytesRef in value with its slice of blob."""
    if isinstance(value, _BytesRef):
        return blob[value.offset : value.offset + value.length]
    if isinstance(value, tuple):
        return tuple(_reinject_bytes(v, blob) for v in value)
    if isinstance(value, list):
        return [_reinject_bytes(v, blob) for v in value]
    if isinstance(value, dict):
        return {k: _reinject_bytes(v, blob) for k, v in value.items()}
    return value


def pack_call(args: tuple, kwargs: dict, frame_id: int) -> bytes:
    """Serialise a call for transport through a shared-memory slot.

    Layout: 4-byte little-endian length of the pickled skeleton, the pickled
    (frame_id, args, kwargs) skeleton, then the concatenated raw bytes arguments.

    Returns:
        bytes: The packed payload.

    Raises:
        TypeError: If an argument has an unsupported type.
    """
    collected: list = []
    skeleton_args = _extract_bytes(args, collected)
    skeleton_kwargs = _extract_bytes(kwargs, collected)
    pickled_skeleton = pickle.dumps(
        (frame_id, skeleton_args, skeleton_kwargs), protocol=pickle.HIGHEST_PROTOCOL
    )
    blob = b"".join(collected)
    return len(pickled_skeleton).to_bytes(4, "little") + pickled_skeleton + blob


def unpack_call(payload: bytes):
    """Parse a payload produced by pack_call.

    Returns:
        tuple: (frame_id, args, kwargs) with bytes arguments restored.
    """
    skeleton_len = int.from_bytes(payload[:4], "little")
    pickled_skeleton = payload[4 : 4 + skeleton_len]
    blob = payload[4 + skeleton_len :]
    frame_id, skeleton_args, skeleton_kwargs = pickle.loads(pickled_skeleton)
    args = _reinject_bytes(skeleton_args, blob)
    kwargs = _reinject_bytes(skeleton_kwargs, blob)
    return frame_id, args, kwargs


class _SlotPool:
    """Fixed-size slots in one shared-memory block plus the queues that coordinate their use.

    A producer takes a slot id from free_slots, writes a packed call into that slot and puts
    (slot_id, frame_id, length) on work_queue; a consumer reads the slot and returns the id to free_slots.

    Attributes:
        num_slots (int): Number of slots.
        slot_size (int): Size of each slot in bytes.
        free_slots: Multiprocessing queue of free slot ids.
        work_queue: Multiprocessing queue of (slot_id, frame_id, length) items awaiting a worker.

    Note:
        The creating process owns the block and must call close() and unlink(); attached processes only call close().
    """

    def __init__(self, shm, num_slots: int, slot_size: int, free_slots, work_queue) -> None:
        """Wrap an existing shared-memory block; use create() or attach() instead of calling this directly.

        Raises:
            ValueError: If slot_size is not positive.
        """
        if slot_size <= 0:
            raise ValueError(f"slot_size_bytes ({slot_size}) must be positive")
        self._shm = shm
        self._buf = shm.buf
        self.num_slots = num_slots
        self.slot_size = slot_size
        self.free_slots = free_slots
        self.work_queue = work_queue

    @classmethod
    def create(
        cls, ctx, name: str, num_slots: int, slot_size: int, work_queue_maxsize: int = 0
    ) -> "_SlotPool":
        """Allocate the shared-memory block and fill free_slots with all slot ids.

        Args:
            ctx: Multiprocessing context used for the queues.
            name (str): Name of the shared-memory block.
            num_slots (int): Number of slots.
            slot_size (int): Bytes per slot.
            work_queue_maxsize (int, optional): Capacity of the work queue; 0 means unbounded. Defaults to 0.

        Returns:
            _SlotPool: The new pool.
        """
        total = num_slots * slot_size
        shm = shared_memory.SharedMemory(name=name, create=True, size=total)
        free_slots = ctx.Queue()
        for i in range(num_slots):
            free_slots.put(i)
        work_queue = ctx.Queue(maxsize=work_queue_maxsize)
        return cls(shm, num_slots, slot_size, free_slots, work_queue)

    @classmethod
    def attach(cls, name: str, num_slots: int, slot_size: int, free_slots, work_queue) -> "_SlotPool":
        """Attach to a block created by another process, using the queues passed from the creator."""
        shm = shared_memory.SharedMemory(name=name, create=False)
        return cls(shm, num_slots, slot_size, free_slots, work_queue)

    @property
    def name(self) -> str:
        """Name of the shared-memory block."""
        return self._shm.name

    @property
    def slot_capacity(self) -> int:
        """Maximum payload size in bytes that fits in one slot."""
        return self.slot_size

    def acquire_slot(self, payload_len: int, timeout: Optional[float] = None) -> int:
        """Take a free slot id.

        Args:
            payload_len (int): Size of the payload that will be written.
            timeout (Optional[float], optional): Seconds to wait; None waits indefinitely. Defaults to None.

        Returns:
            int: The slot id.

        Raises:
            ValueError: If payload_len exceeds the slot capacity.
            queue.Empty: If no slot becomes free within timeout.
        """
        if payload_len > self.slot_capacity:
            raise ValueError(
                f"call payload of {payload_len} bytes exceeds this pool's "
                f"per-slot capacity of {self.slot_capacity} bytes -- construct "
                "AxVisionClient/AxVlmClient with a larger shm_slot_size_bytes"
            )
        if timeout is None:
            return self.free_slots.get()
        return self.free_slots.get(timeout=timeout)

    def write_slot(self, slot_id: int, payload: bytes) -> None:
        """Copy payload to the start of a slot; the caller must have checked its size."""
        start = slot_id * self.slot_size
        self._buf[start : start + len(payload)] = payload

    def read_slot(self, slot_id: int, length: int) -> bytes:
        """Return the first length bytes of a slot as a copy."""
        start = slot_id * self.slot_size
        return bytes(self._buf[start : start + length])

    def release_slot(self, slot_id: int) -> None:
        """Return a slot id to the free queue."""
        self.free_slots.put(slot_id)

    def close(self) -> None:
        """Release this process's view of the shared memory."""
        self._buf.release()
        self._shm.close()

    def unlink(self) -> None:
        """Remove the shared-memory block from the system; call once, from the creating process."""
        self._shm.unlink()


class _WorkerChannel:
    """Single-producer, single-consumer ring of length-prefixed slots in shared memory.

    Each slot holds an 8-byte little-endian length followed by the payload. Read and write
    positions are shared counters guarded by one lock.

    Note:
        Not used anywhere in the client; _SlotPool is the transport the engine uses.
    """

    def __init__(self, shm, ring_size: int, slot_size: int, write_ptr, read_ptr, lock) -> None:
        """Wrap an existing shared-memory block; use create() or attach() instead of calling this directly.

        Raises:
            ValueError: If slot_size does not leave room for the 8-byte length header.
        """
        if slot_size <= _LEN_STRUCT.size:
            raise ValueError(
                f"slot_size_bytes ({slot_size}) must be larger than the "
                f"{_LEN_STRUCT.size}-byte length header"
            )
        self._shm = shm
        self._buf = shm.buf
        self.ring_size = ring_size
        self.slot_size = slot_size
        self._payload_capacity = slot_size - _LEN_STRUCT.size
        self._write_ptr = write_ptr
        self._read_ptr = read_ptr
        self._lock = lock

    @classmethod
    def create(cls, ctx, name: str, ring_size: int, slot_size: int) -> "_WorkerChannel":
        """Allocate the shared-memory block and the shared counters and lock."""
        total = ring_size * slot_size
        shm = shared_memory.SharedMemory(name=name, create=True, size=total)
        write_ptr = ctx.Value(ctypes.c_ulonglong, 0, lock=False)
        read_ptr = ctx.Value(ctypes.c_ulonglong, 0, lock=False)
        lock = ctx.Lock()
        return cls(shm, ring_size, slot_size, write_ptr, read_ptr, lock)

    @classmethod
    def attach(cls, name: str, ring_size: int, slot_size: int, write_ptr, read_ptr, lock) -> "_WorkerChannel":
        """Attach to a block created by another process, using the counters and lock passed from the creator."""
        shm = shared_memory.SharedMemory(name=name, create=False)
        return cls(shm, ring_size, slot_size, write_ptr, read_ptr, lock)

    @property
    def name(self) -> str:
        """Name of the shared-memory block."""
        return self._shm.name

    @property
    def write_ptr(self):
        """Shared counter of slots written so far."""
        return self._write_ptr

    @property
    def read_ptr(self):
        """Shared counter of slots read so far."""
        return self._read_ptr

    @property
    def lock(self):
        """Lock guarding both counters and the slot contents."""
        return self._lock

    @property
    def payload_capacity(self) -> int:
        """Maximum payload size in bytes per slot (slot size minus the length header)."""
        return self._payload_capacity

    def write(self, payload: bytes) -> None:
        """Append a payload, polling until a slot is free.

        Raises:
            ValueError: If the payload does not fit in a slot.
        """
        if len(payload) > self._payload_capacity:
            raise ValueError(
                f"call payload of {len(payload)} bytes exceeds this channel's "
                f"per-slot capacity of {self._payload_capacity} bytes -- construct "
                "AxVisionClient/AxVlmClient with a larger shm_slot_size_bytes"
            )
        while True:
            with self._lock:
                if self._write_ptr.value - self._read_ptr.value < self.ring_size:
                    slot = self._write_ptr.value % self.ring_size
                    self._write_slot(slot, payload)
                    self._write_ptr.value += 1
                    return
            time.sleep(_POLL_BACKOFF_SEC)

    def try_read(self) -> Optional[bytes]:
        """Pop the oldest payload, or return None if the ring is empty."""
        with self._lock:
            if self._read_ptr.value >= self._write_ptr.value:
                return None
            slot = self._read_ptr.value % self.ring_size
            payload = self._read_slot(slot)
            self._read_ptr.value += 1
            return payload

    def _write_slot(self, slot: int, payload: bytes) -> None:
        """Write the length header and payload into a slot."""
        start = slot * self.slot_size
        self._buf[start : start + _LEN_STRUCT.size] = _LEN_STRUCT.pack(len(payload))
        data_start = start + _LEN_STRUCT.size
        self._buf[data_start : data_start + len(payload)] = payload

    def _read_slot(self, slot: int) -> bytes:
        """Read a slot's payload using its length header."""
        start = slot * self.slot_size
        (length,) = _LEN_STRUCT.unpack(bytes(self._buf[start : start + _LEN_STRUCT.size]))
        data_start = start + _LEN_STRUCT.size
        return bytes(self._buf[data_start : data_start + length])

    def close(self) -> None:
        """Release this process's view of the shared memory."""
        self._buf.release()
        self._shm.close()

    def unlink(self) -> None:
        """Remove the shared-memory block from the system."""
        self._shm.unlink()
