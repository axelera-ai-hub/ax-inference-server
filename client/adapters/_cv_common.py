"""Helpers shared by the OpenCV-based source adapters."""
from __future__ import annotations

import cv2
import numpy as np

from .base import SourceAdapterError


def encode_bgr_to_jpeg(frame: np.ndarray, *, quality: int = 90) -> bytes:
    """Encode a BGR image as JPEG bytes.

    Args:
        frame (np.ndarray): BGR image as produced by OpenCV.
        quality (int, optional): JPEG quality passed to OpenCV (0-100). Defaults to 90.

    Returns:
        bytes: The JPEG-encoded image.

    Raises:
        SourceAdapterError: If cv2.imencode reports failure.
    """
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise SourceAdapterError("cv2.imencode('.jpg', ...) failed")
    return buf.tobytes()
