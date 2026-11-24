# AxTrack

## Overview
`AxTrack` is a multi-object tracker adapter for inference results. It converts a frame's detections to `supervision` `Detections`, runs them through a tracker and returns `TrackedDetection` objects. It uses `ByteTrackTracker` from the `trackers` package unless you pass another tracker with `update(detections, timestamp=...)` and `reset()`. The module has no async variant. The `client/tracker` directory is not a package. Put it on `sys.path` and import `from ax_track import AxTrack`.

## Attributes
| Attribute | Type | Description |
|---|---|---|
| none public | none | State is held in private attributes. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `__init__(tracker, class_ids, class_names, frame_rate)` | Creates the adapter. | this page |
| `Track(frame_result, timestamp)` | Tracks one frame. | [AxTrack.Track](AxTrack.Track.md) |
| `reset()` | Clears the tracker state, for example when a new video starts. | this page |

## Initialization
```python
AxTrack(
    tracker=None,
    class_ids: set[int] | None = None,
    class_names: dict[int, str] | None = None,
    frame_rate: float = 30.0,
)
```

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `tracker` | object | `None` | no | Tracker to use. A `ByteTrackTracker` is created if `None`. |
| `class_ids` | `set[int] \| None` | `None` | no | Track only these classes. `None` tracks all classes. |
| `class_names` | `dict[int, str] \| None` | `None` | no | Class id to label map for the `label` field. |
| `frame_rate` | `float` | `30.0` | no | Frame rate for the default `ByteTrackTracker`. |

## Lifecycle
The object holds tracker state across frames. Keep one instance per video stream. Call `Track()` once per frame in order. Call `reset()` between videos. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [TrackedDetection](TrackedDetection.md) | Output element of `Track`. |
| [to_proto_detection](to_proto_detection.md) | Writes a tracked detection into a message. |

## Source Reference
`client/tracker/ax_track.py::AxTrack` (lines 48-133)
