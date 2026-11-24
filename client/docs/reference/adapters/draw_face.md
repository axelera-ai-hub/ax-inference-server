# draw_face

## Summary

Draws face boxes captioned `face` and landmark dots.

## Detailed Description

### Behavior

When a detection has `face_bbox`, the function draws a cyan rectangle (BGR `(255, 255, 0)`) and writes `face` below it. For each entry in `face_landmarks` it draws a filled dot of radius 2.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_face(raw: np.ndarray, detections) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| detections | iterable of detection messages | none | yes | Messages with optional `face_bbox` (`x`, `y`, `w`, `h`) and a `face_landmarks` list. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_face

draw_face(frame.raw, response.detections)
```

## Edge Cases

- A detection with neither `face_bbox` nor landmarks is skipped.
- Landmarks are drawn even when `face_bbox` is absent.

## Related APIs

| API | Relationship |
|---|---|
| [draw_detections](draw_detections.md) | Sibling overlay for boxes. |
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_face` (lines 163-184)
