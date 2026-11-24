# Tracker reference

## Overview
The `client/tracker` module adds persistent track ids to detections across video frames. It runs locally and makes no network calls. It wraps `ByteTrackTracker` from the `trackers` package and uses `supervision`. Install both with `client/setup.sh --tracker`. See the [client concept page](../../client/client.md).

## Pages
| Page | Kind | Summary |
|---|---|---|
| [AxTrack](AxTrack.md) | class | Tracker adapter that keeps state across frames. |
| [AxTrack.Track](AxTrack.Track.md) | function | Updates the tracker with one frame and returns tracked detections. |
| [TrackedDetection](TrackedDetection.md) | class | Dataclass for one detection with a track id. |
| [to_proto_detection](to_proto_detection.md) | function | Copies a detection message and writes the tracked box and id into it. |

## Quick Example
```python
from ax_track import AxTrack  # client/tracker must be on sys.path

tracker = AxTrack(class_ids={0}, class_names={0: "person"})
for frame_result in frame_results:
    for td in tracker.Track(frame_result):
        print(td.track_id, td.x, td.y, td.w, td.h)
```
