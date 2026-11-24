"""Object tracking helper built on the supervision/trackers packages.

Exposes AxTrack, which assigns persistent ids to detections across frames, the TrackedDetection
it returns, and to_proto_detection for writing the result back into a detection message.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import supervision as sv


@dataclass
class TrackedDetection:
    """One detection with a persistent track id, in pixel coordinates.

    Attributes:
        track_id (int): Tracker-assigned id, or -1 if the tracker returned none.
        x (int): Left edge of the box.
        y (int): Top edge of the box.
        w (int): Box width.
        h (int): Box height.
        score (float): Detection confidence.
        class_id (int): Class index, or -1 if the tracker returned none.
        label (str): Class name from the class_names map, or the class id as text.
    """
    track_id: int
    x: int
    y: int
    w: int
    h: int
    score: float
    class_id: int
    label: str


def _xywh_to_xyxy(x: int, y: int, w: int, h: int) -> tuple[float, float, float, float]:
    """Convert a left/top/width/height box to corner coordinates (x1, y1, x2, y2)."""
    return float(x), float(y), float(x + w), float(y + h)


def _xyxy_to_xywh(x1: float, y1: float, x2: float, y2: float) -> tuple[int, int, int, int]:
    """Convert corner coordinates to a rounded left/top/width/height box."""
    return int(round(x1)), int(round(y1)), int(round(x2 - x1)), int(round(y2 - y1))


class AxTrack:
    """Multi-object tracker adapter for inference results.

    Converts a frame's detections to supervision Detections, runs them through a tracker and
    returns TrackedDetection objects. Uses ByteTrackTracker from the 'trackers' package unless
    another tracker with update(detections, timestamp=...) and reset() is supplied.

    Note:
        Holds tracker state across frames; keep one instance per video stream and call Track() once per frame in order.
    """
    def __init__(
        self,
        tracker=None,
        class_ids: set[int] | None = None,
        class_names: dict[int, str] | None = None,
        frame_rate: float = 30.0,
    ) -> None:
        """Create the tracker adapter.

        Args:
            tracker (optional): Tracker instance to use. If None, a ByteTrackTracker is created.
            class_ids (set[int] | None, optional): If given, only detections of these classes are tracked.
                Defaults to None (all classes).
            class_names (dict[int, str] | None, optional): Class id to label mapping used for the label field. Defaults to None.
            frame_rate (float, optional): Frame rate passed to the default ByteTrackTracker. Defaults to 30.0.
        """
        if tracker is None:
            from trackers import ByteTrackTracker

            tracker = ByteTrackTracker(frame_rate=frame_rate)
        self._tracker = tracker
        self._class_ids = class_ids
        self._class_names = class_names or {}

    def Track(self, frame_result, timestamp: float | None = None) -> list[TrackedDetection]:
        """Update the tracker with one frame's detections.

        Args:
            frame_result: Inference result whose detections have bbox (x, y, w, h), score and class_id.
            timestamp (float | None, optional): Frame time passed to the tracker. Defaults to None.

        Returns:
            list[TrackedDetection]: Tracked objects in the tracker's output order. track_id and class_id are -1,
            and score is 0.0, when the tracker output lacks the corresponding array.
        """
        detections = frame_result.detections
        if self._class_ids is not None:
            detections = [d for d in detections if d.class_id in self._class_ids]

        n = len(detections)
        xyxy = np.zeros((n, 4), dtype=np.float32)
        confidence = np.zeros(n, dtype=np.float32)
        class_id = np.zeros(n, dtype=int)
        for i, det in enumerate(detections):
            bbox = det.bbox
            xyxy[i] = _xywh_to_xyxy(bbox.x, bbox.y, bbox.w, bbox.h)
            confidence[i] = det.score
            class_id[i] = det.class_id

        sv_detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        tracked = self._tracker.update(sv_detections, timestamp=timestamp)

        out: list[TrackedDetection] = []
        for i in range(len(tracked)):
            x1, y1, x2, y2 = tracked.xyxy[i]
            x, y, w, h = _xyxy_to_xywh(x1, y1, x2, y2)
            cid = int(tracked.class_id[i]) if tracked.class_id is not None else -1
            score = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            tid = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else -1
            out.append(
                TrackedDetection(
                    track_id=tid,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    score=score,
                    class_id=cid,
                    label=self._class_names.get(cid, str(cid)),
                )
            )
        return out

    def reset(self) -> None:
        """Clear the tracker's internal state, e.g. when a new video starts."""
        self._tracker.reset()


def to_proto_detection(td: TrackedDetection, source):
    """Copy a source detection message and overwrite its box and track id from a tracked detection.

    Args:
        td (TrackedDetection): Tracked detection supplying the box and id.
        source: Original detection message; it is not modified.

    Returns:
        A new message of the same type as source with bbox set from td and track_id set to str(td.track_id).
    """
    out = type(source)()
    out.CopyFrom(source)
    out.bbox.x, out.bbox.y, out.bbox.w, out.bbox.h = td.x, td.y, td.w, td.h
    out.track_id = str(td.track_id)
    return out
