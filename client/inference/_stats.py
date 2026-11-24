"""Windowed throughput and latency statistics for client processes.

Exposes WindowedStats, which prints a periodic one-line status report.
"""
from __future__ import annotations

import os
import time


class WindowedStats:
    """Per-process throughput and latency counters that print a status line every interval.

    Collects totals for the whole run and per-window figures (FPS, average detections, latency
    min/avg/max). A report is printed to stdout from update() once the interval has elapsed.

    Attributes:
        pid (int): Process id shown in the report.
        interval (float): Seconds between reports.
        current_window (int | None): Optional window size shown in the report when set.
        current_ceiling (int | None): Optional ceiling shown in the report when set.
        total_count (int): Results recorded via update().
        total_detections (int): Sum of num_detections over all updates.
        total_keypoints (int): Sum of num_keypoints over all updates.
        total_segmentations (int): Sum of num_segmentations over all updates.
        failed_count (int): Failures recorded.
        retried_count (int): Retries recorded.
        retry_exhausted_count (int): Frames that ran out of retries.
        start_time (float): time.time() when the object was created.

    Note:
        Not thread-safe. Not referenced elsewhere in the client package.
    """

    def __init__(self, report_interval_sec: float = 2.0) -> None:
        """Start the first window now.

        Args:
            report_interval_sec (float, optional): Seconds between status lines. Defaults to 2.0.
        """
        self.pid = os.getpid()
        self.interval = report_interval_sec
        self.current_window: int | None = None
        self.current_ceiling: int | None = None

        self._window_start = time.time()
        self._window_count = 0
        self._window_detections = 0
        self._window_latencies: list[float] = []

        self.total_count = 0
        self.total_detections = 0
        self.total_keypoints = 0
        self.total_segmentations = 0
        self.failed_count = 0
        self.retried_count = 0
        self.retry_exhausted_count = 0
        self.start_time = time.time()

    def update(self, latency_sec: float, num_detections: int = 0,
               num_keypoints: int = 0, num_segmentations: int = 0) -> None:
        """Record one completed result and print a report if the window interval has elapsed.

        Args:
            latency_sec (float): Latency of this result in seconds.
            num_detections (int, optional): Detections in the result. Defaults to 0.
            num_keypoints (int, optional): Keypoints in the result. Defaults to 0.
            num_segmentations (int, optional): Segmentations in the result. Defaults to 0.
        """
        self._window_count += 1
        self.total_count += 1
        self._window_detections += num_detections
        self.total_detections += num_detections
        self.total_keypoints += num_keypoints
        self.total_segmentations += num_segmentations
        self._window_latencies.append(latency_sec)

        now = time.time()
        if now - self._window_start >= self.interval:
            self._print_report(now - self._window_start)
            self._reset_window(now)

    def record_failure(self) -> None:
        """Count one failed result."""
        self.failed_count += 1

    def record_retry(self) -> None:
        """Count one retry."""
        self.retried_count += 1

    def record_retry_exhausted(self) -> None:
        """Count one frame whose retries were exhausted."""
        self.retry_exhausted_count += 1

    def set_window(self, window: int) -> None:
        """Set the window value shown in reports."""
        self.current_window = window

    def set_ceiling(self, ceiling: int) -> None:
        """Set the ceiling value shown in reports."""
        self.current_ceiling = ceiling

    def _print_report(self, elapsed: float) -> None:
        """Print one '[Status]' line with totals and this window's FPS, average detections and latency in ms."""
        fps = self._window_count / elapsed if elapsed > 0 else 0.0
        avg_dets = (
            self._window_detections / self._window_count
            if self._window_count > 0
            else 0.0
        )

        if self._window_latencies:
            avg_lat = sum(self._window_latencies) / len(self._window_latencies) * 1000
            min_lat = min(self._window_latencies) * 1000
            max_lat = max(self._window_latencies) * 1000
        else:
            avg_lat = min_lat = max_lat = 0.0

        window_field = (
            f" | Window: {self.current_window:3d}" if self.current_window is not None else ""
        )
        ceiling_field = (
            f" | Ceiling: {self.current_ceiling:3d}" if self.current_ceiling is not None else ""
        )
        print(
            f"[Status] PID: {self.pid} | "
            f"Total: {self.total_count:6d} | "
            f"Inst FPS: {fps:6.2f} | "
            f"Avg Dets: {avg_dets:5.1f} | "
            f"Lat (ms): Avg {avg_lat:6.2f} / Min {min_lat:4.0f} / Max {max_lat:4.0f}"
            f"{window_field}"
            f"{ceiling_field}"
        )

    def _reset_window(self, now: float) -> None:
        """Start a new window at time now, clearing the per-window counters."""
        self._window_start = now
        self._window_count = 0
        self._window_detections = 0
        self._window_latencies = []
