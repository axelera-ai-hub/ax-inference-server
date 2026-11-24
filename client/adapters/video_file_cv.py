from __future__ import annotations

import os
from typing import Optional

import cv2

from ._cv_common import encode_bgr_to_jpeg
from .base import Frame, SourceAdapter, SourceAdapterError

_FALLBACK_FPS = 30.0


class VideoFileAdapterCV(SourceAdapter):
    """Source adapter that reads frames from a video file with cv2.VideoCapture.

    Optionally loops back to the first frame at end of file. When no target_fps is
    given, the file's native frame rate is used after open().
    """

    source_kind = "video_file"

    def __init__(
        self,
        path: str,
        *,
        target_fps: Optional[float] = None,
        loop: bool = True,
        jpeg_quality: int = 90,
    ) -> None:
        """Store the video path and read settings; the file is opened in open().

        Args:
            path (str): Path of the video file.
            target_fps (Optional[float], optional): Desired read rate. If None, the native
                FPS reported by the file is used, falling back to 30.0. Defaults to None.
            loop (bool, optional): Restart from the first frame at end of file instead of
                returning None. Defaults to True.
            jpeg_quality (int, optional): JPEG quality for encoded frames. Defaults to 90.
        """
        super().__init__(target_fps=target_fps if target_fps is not None else _FALLBACK_FPS)
        self._path = path
        self._requested_fps = target_fps
        self._loop = loop
        self._jpeg_quality = jpeg_quality
        self._cap: Optional[cv2.VideoCapture] = None

    def _open(self) -> None:
        """Open the video file and, if no FPS was requested, adopt its native FPS.

        Raises:
            SourceAdapterError: If the file cannot be opened.
        """
        cap = cv2.VideoCapture(self._path)
        if not cap.isOpened():
            raise SourceAdapterError(f"could not open video file: {self._path}")
        self._cap = cap
        if self._requested_fps is None:
            native_fps = cap.get(cv2.CAP_PROP_FPS)
            self.target_fps = native_fps if native_fps and native_fps > 0 else _FALLBACK_FPS

    def _close(self) -> None:
        """Release the VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]:
        """Read the next video frame, rewinding once at end of file when looping.

        Returns:
            Optional[Frame]: The frame, or None at end of file when loop is False.

        Raises:
            SourceAdapterError: If a read still fails right after rewinding.
        """
        assert self._cap is not None
        ok, raw = self._cap.read()
        if not ok:
            if not self._loop:
                return None
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, raw = self._cap.read()
            if not ok:
                raise SourceAdapterError(f"video file produced no frames after looping: {self._path}")
        encoded = encode_bgr_to_jpeg(raw, quality=self._jpeg_quality) if need_encoded else b''
        return Frame(encoded=encoded, raw=raw)

    @property
    def display_name(self) -> str:
        """File name of the video without its directory."""
        return os.path.basename(self._path)
