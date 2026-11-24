# TrackedDetection

## Overview
`TrackedDetection` is a dataclass for one detection with a persistent track id, in pixel coordinates. `AxTrack.Track` returns a list of them.

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `track_id` | `int` | Tracker-assigned id, or -1 if the tracker returned none. |
| `x` | `int` | Left edge of the box. |
| `y` | `int` | Top edge of the box. |
| `w` | `int` | Box width. |
| `h` | `int` | Box height. |
| `score` | `float` | Detection confidence. |
| `class_id` | `int` | Class index, or -1 if the tracker returned none. |
| `label` | `str` | Name from the `class_names` map, or the class id as text. |

## Methods
| Method | Summary | Page |
|---|---|---|
| none | The class only holds fields. | none |

## Initialization
All eight fields are required.

## Lifecycle
The object is a plain dataclass with no resources.

## Related Classes
| Class | Relationship |
|---|---|
| [AxTrack](AxTrack.md) | Produces the objects. |

## Source Reference
`client/tracker/ax_track.py::TrackedDetection` (lines 14-35)
