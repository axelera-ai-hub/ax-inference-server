from __future__ import annotations

import glob
from dataclasses import dataclass
from typing import List, Optional, Union

import cv2

from ._cv_common import encode_bgr_to_jpeg
from .base import Frame, SourceAdapter, SourceAdapterError

_DEFAULT_TARGET_FPS = 30.0


@dataclass
class WebcamDeviceInfo:
    """Description of one V4L2 capture device found under /dev.

    Attributes:
        path (str): Device node, e.g. '/dev/video0'.
        index (int): Numeric suffix of the device node.
        display_name (str): Label shown to the user, e.g. 'USB 0'.
    """

    path: str
    index: int
    display_name: str


class WebcamAdapterCV(SourceAdapter):
    """Source adapter that reads live frames from a camera with cv2.VideoCapture.

    A failed read is treated as a disconnected device and raises; the stream never ends normally.
    """

    source_kind = "webcam"

    def __init__(
        self,
        device: Union[int, str],
        *,
        target_fps: float = _DEFAULT_TARGET_FPS,
        jpeg_quality: int = 90,
    ) -> None:
        """Store the device and read settings; the camera is opened in open().

        Args:
            device (Union[int, str]): Camera index or device path such as '/dev/video0'.
            target_fps (float, optional): Frame rate requested from the camera. Defaults to 30.0.
            jpeg_quality (int, optional): JPEG quality for encoded frames. Defaults to 90.
        """
        super().__init__(target_fps=target_fps)
        self._device = device
        self._jpeg_quality = jpeg_quality
        self._cap: Optional[cv2.VideoCapture] = None

    def _open(self) -> None:
        """Open the camera and request target_fps from the driver.

        Raises:
            SourceAdapterError: If the device cannot be opened.
        """
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            raise SourceAdapterError(f"could not open webcam device: {self._device}")
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        self._cap = cap

    def _close(self) -> None:
        """Release the VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]:
        """Grab the next camera frame.

        Raises:
            SourceAdapterError: If the read fails (device may be disconnected).
        """
        assert self._cap is not None
        ok, raw = self._cap.read()
        if not ok:
            raise SourceAdapterError(f"webcam read failed, device may be disconnected: {self._device}")
        encoded = encode_bgr_to_jpeg(raw, quality=self._jpeg_quality) if need_encoded else b''
        return Frame(encoded=encoded, raw=raw)

    @property
    def display_name(self) -> str:
        """Label such as 'USB 0', or the raw device string if it has no /dev/videoN index."""
        if isinstance(self._device, int):
            return f"USB {self._device}"
        index = _parse_video_index(self._device)
        return f"USB {index}" if index is not None else self._device

    @staticmethod
    def list_devices(*, probe: bool = True) -> List[WebcamDeviceInfo]:
        """List /dev/video* devices, sorted by path.

        Args:
            probe (bool, optional): Open each device with OpenCV and skip those that
                cannot be opened. Defaults to True.

        Returns:
            List[WebcamDeviceInfo]: One entry per device whose path ends in a number.
        """
        devices: List[WebcamDeviceInfo] = []
        for path in sorted(glob.glob("/dev/video*")):
            index = _parse_video_index(path)
            if index is None:
                continue
            if probe:
                cap = cv2.VideoCapture(index)
                is_capture = cap.isOpened()
                cap.release()
                if not is_capture:
                    continue
            devices.append(WebcamDeviceInfo(path=path, index=index, display_name=f"USB {index}"))
        return devices


def _parse_video_index(path: str) -> Optional[int]:
    """Extract N from a '/dev/videoN' path, or return None if the path does not match."""
    prefix = "/dev/video"
    if not path.startswith(prefix):
        return None
    suffix = path[len(prefix):]
    return int(suffix) if suffix.isdigit() else None
