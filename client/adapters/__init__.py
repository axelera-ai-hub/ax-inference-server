"""Frame source adapters: OpenCV-backed readers for video files, still images and webcams.

Re-exports the SourceAdapter base types and the concrete adapters from this package.
"""
from __future__ import annotations

from .base import Frame, SourceAdapter, SourceAdapterError
from .image_cv import ImageAdapterCV
from .video_file_cv import VideoFileAdapterCV
from .webcam_cv import WebcamAdapterCV, WebcamDeviceInfo

__all__ = [
    "Frame",
    "SourceAdapter",
    "SourceAdapterError",
    "VideoFileAdapterCV",
    "ImageAdapterCV",
    "WebcamAdapterCV",
    "WebcamDeviceInfo",
]
