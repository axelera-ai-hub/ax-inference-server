from __future__ import annotations

import os
from typing import Optional

import cv2
import numpy as np

from ._cv_common import encode_bgr_to_jpeg
from .base import Frame, SourceAdapter, SourceAdapterError


class ImageAdapterCV(SourceAdapter):
    """Source adapter that serves one still image repeatedly.

    The file is decoded and JPEG-encoded once in open(); every read returns the same
    cached buffers. End of stream is never reported.

    Note:
        need_encoded is ignored: frames always carry the cached JPEG bytes.
    """

    source_kind = "image"

    def __init__(self, path: str, *, target_fps: float = 30.0, jpeg_quality: int = 90) -> None:
        """Store the image path and encoding settings; the file is read in open().

        Args:
            path (str): Path of the image file.
            target_fps (float, optional): Desired read rate. Defaults to 30.0.
            jpeg_quality (int, optional): JPEG quality for the cached encoding. Defaults to 90.
        """
        super().__init__(target_fps=target_fps)
        self._path = path
        self._jpeg_quality = jpeg_quality
        self._raw: Optional[np.ndarray] = None
        self._encoded: Optional[bytes] = None

    def _open(self) -> None:
        """Decode the image as BGR and cache its JPEG encoding.

        Raises:
            SourceAdapterError: If the file cannot be read as an image.
        """
        raw = cv2.imread(self._path, cv2.IMREAD_COLOR)
        if raw is None:
            raise SourceAdapterError(f"could not read image file: {self._path}")
        self._raw = raw
        self._encoded = encode_bgr_to_jpeg(raw, quality=self._jpeg_quality)

    def _close(self) -> None:
        """Drop the cached image buffers."""
        self._raw = None
        self._encoded = None

    def _read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]:
        """Return a Frame wrapping the cached image; never returns None."""
        assert self._raw is not None and self._encoded is not None
        return Frame(encoded=self._encoded, raw=self._raw)

    @property
    def display_name(self) -> str:
        """File name of the image without its directory."""
        return os.path.basename(self._path)
