# to_proto_detection

## Summary
`to_proto_detection` copies a source detection message and overwrites its box and track id from a tracked detection.

## Detailed Description
### Behavior
The function creates a new message of the same type as `source` and copies `source` into it. It sets `bbox.x`, `bbox.y`, `bbox.w` and `bbox.h` from `td`. It sets `track_id` to `str(td.track_id)`. The function does not modify `source`.

### Concurrency
Concurrency behavior depends on the underlying runtime.

### Constraints
`source` must have a `bbox` with `x`, `y`, `w`, `h` and a `track_id` field.

## Signature
```python
to_proto_detection(td: TrackedDetection, source)
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `td` | `TrackedDetection` | none | yes | Supplies the box and id. |
| `source` | message | none | yes | Original detection message. |

## Returns
A new message of the same type as `source`.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `AttributeError` | `source` lacks `bbox` or `track_id`. | Pass a detection message. |

## Usage Examples
### Basic
```python
from ax_track import AxTrack, to_proto_detection

tracked = tracker.Track(frame_result)
msg = to_proto_detection(tracked[0], frame_result.detections[0])
```

## Edge Cases
- The tracker can reorder detections, so index pairing is not reliable.

## Related APIs
| API | Relationship |
|---|---|
| [TrackedDetection](TrackedDetection.md) | Input type. |
| [AxTrack.Track](AxTrack.Track.md) | Produces the input. |

## Source Reference
`client/tracker/ax_track.py::to_proto_detection` (lines 136-150)
