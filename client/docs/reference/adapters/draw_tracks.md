# draw_tracks

## Summary

Draws tracked-object boxes with `#id label` captions onto a frame.

## Detailed Description

### Behavior

Each track id maps to a fixed colour computed from the id. The function draws the box and a filled caption in that colour. Tracks with a negative `track_id` are skipped.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_tracks(raw: np.ndarray, tracked) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| tracked | iterable of tracked objects | none | yes | Objects with `track_id`, `label`, `x`, `y`, `w` and `h`. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_tracks

draw_tracks(frame.raw, tracked_objects)
```

## Edge Cases

- A track with `track_id < 0` is skipped.
- The same id always yields the same colour.

## Related APIs

| API | Relationship |
|---|---|
| [draw_detections](draw_detections.md) | Draws untracked detection boxes. |
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_tracks` (lines 47-66)
