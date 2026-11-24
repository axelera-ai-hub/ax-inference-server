# AxTrack.Track

## Summary
`Track` updates the tracker with one frame's detections and returns the tracked objects.

## Detailed Description
### Behavior
The method filters detections by `class_ids` if set. It converts each box from `(x, y, w, h)` to corner coordinates. It builds `sv.Detections` and calls `tracker.update(detections, timestamp=timestamp)`. It converts the tracker output back to `TrackedDetection` objects in the tracker's output order. `label` comes from `class_names`, or is the class id as text.

### Concurrency
Concurrency behavior depends on the underlying runtime. Call the method from one thread per stream, once per frame, in order.

### Constraints
Each detection must have `bbox` with `x`, `y`, `w`, `h`, plus `score` and `class_id`.

## Signature
```python
AxTrack.Track(frame_result, timestamp: float | None = None) -> list[TrackedDetection]
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `frame_result` | object | none | yes | Inference result with a `detections` list. |
| `timestamp` | `float \| None` | `None` | no | Frame time passed to the tracker. |

## Returns
`list[TrackedDetection]`. `track_id` and `class_id` are -1, and `score` is 0.0, when the tracker output lacks the matching array.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `AttributeError` | `frame_result` has no `detections`, or a detection lacks the fields above. | Pass a `FrameResult`. Behavior inferred from code inspection. |

## Usage Examples
### Basic
```python
from ax_track import AxTrack

tracker = AxTrack(class_names={0: "person"})
tracked = tracker.Track(frame_result)
```

## Edge Cases
- An empty detection list returns the tracker's output for zero detections.
- Frames with `class_ids` filtering drop other classes before tracking.

## Related APIs
| API | Relationship |
|---|---|
| [AxTrack](AxTrack.md) | Owner class. |
| [TrackedDetection](TrackedDetection.md) | Return element. |
| [to_proto_detection](to_proto_detection.md) | Converts an element back to a message. |

## Source Reference
`client/tracker/ax_track.py::AxTrack.Track` (lines 82-129)
