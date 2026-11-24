"""Abstract frame-source interface shared by the video, image and webcam adapters.

Exposes SourceAdapter, the Frame container it yields and SourceAdapterError.
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


class SourceAdapterError(RuntimeError):
    """Raised when an adapter cannot open, read from or encode its source."""

    pass


@dataclass
class Frame:
    """One captured frame handed to the inference client.

    Attributes:
        encoded (bytes): JPEG-encoded image. Empty when the reader was called with need_encoded=False.
        raw (np.ndarray): Decoded BGR image.
        captured_at (float): time.monotonic() timestamp taken when the Frame was constructed.
        sequence (int): Per-adapter counter, assigned by SourceAdapter.read_frame (starts at 0).
    """

    encoded: bytes
    raw: np.ndarray
    captured_at: float = field(default_factory=time.monotonic)
    sequence: int = 0


class SourceAdapter(abc.ABC):
    """Base class for objects that produce Frames from a video, image or camera source.

    Subclasses implement _open, _close, _read_frame and display_name. The base class
    tracks the open state, numbers the frames and works as a context manager.

    Attributes:
        source_kind (str): Short label for the source type, e.g. 'video_file'. Defaults to 'unknown'.

    Note:
        Not thread-safe; use one adapter from one thread at a time.
    """

    source_kind: str = "unknown"

    def __init__(self, *, target_fps: float) -> None:
        """Initialise the adapter in the closed state.

        Args:
            target_fps (float): Desired read rate in frames per second. Must be positive.

        Raises:
            ValueError: If target_fps is not positive.
        """
        if target_fps <= 0:
            raise ValueError(f"target_fps must be positive, got {target_fps}")
        self._target_fps = target_fps
        self._sequence = 0
        self._opened = False

    def open(self) -> None:
        """Open the underlying source; does nothing if already open."""
        if self._opened:
            return
        self._open()
        self._opened = True

    def close(self) -> None:
        """Release the underlying source; does nothing if not open."""
        if not self._opened:
            return
        self._close()
        self._opened = False

    def __enter__(self) -> "SourceAdapter":
        """Open the adapter and return it."""
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Close the adapter; exceptions from the with-body are not suppressed."""
        self.close()

    @property
    def is_open(self) -> bool:
        """Report whether open() has succeeded and close() has not been called since."""
        return self._opened

    def read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]:
        """Read the next frame from the source and number it.

        Args:
            need_encoded (bool, optional): Whether to JPEG-encode the frame. Subclasses may
                return an empty Frame.encoded when False. Defaults to True.

        Returns:
            Optional[Frame]: The next frame, or None when the source is exhausted.

        Raises:
            SourceAdapterError: If the adapter is not open or the subclass fails to read.
        """
        if not self._opened:
            raise SourceAdapterError(f"{type(self).__name__}.read_frame() called before open()")
        frame = self._read_frame(need_encoded=need_encoded)
        if frame is None:
            return None
        frame.sequence = self._sequence
        self._sequence += 1
        return frame

    @property
    def target_fps(self) -> float:
        """Desired read rate in frames per second."""
        return self._target_fps

    @target_fps.setter
    def target_fps(self, value: float) -> None:
        """Set the desired read rate; raises ValueError if value is not positive."""
        if value <= 0:
            raise ValueError(f"target_fps must be positive, got {value}")
        self._target_fps = value

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """Human-readable name of the source, shown in the UI."""
        pass

    @abc.abstractmethod
    def _open(self) -> None:
        """Acquire the underlying resource; called once by open()."""
        ...

    @abc.abstractmethod
    def _close(self) -> None:
        """Release the underlying resource; called once by close()."""
        ...

    @abc.abstractmethod
    def _read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]:
        """Produce the next Frame, or None at end of stream; read_frame sets its sequence."""
        ...
