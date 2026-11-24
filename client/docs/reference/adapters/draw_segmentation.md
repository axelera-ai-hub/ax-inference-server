# draw_segmentation

## Summary

Draws translucent filled segmentation polygons with outlines.

## Detailed Description

### Behavior

The function collects one polygon per detection from the `segmentation` point list. It fills all polygons on a copy of the frame and blends the copy back with alpha 125/255. It then draws a magenta outline (BGR `(255, 0, 255)`) around each polygon.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_segmentation(raw: np.ndarray, detections) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| detections | iterable of detection messages | none | yes | Messages with a `segmentation` list of points with `x` and `y`. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_segmentation

draw_segmentation(frame.raw, response.detections)
```

## Edge Cases

- Polygons with fewer than 3 points are skipped.
- If no polygon qualifies, the function returns without copying the frame.

## Related APIs

| API | Relationship |
|---|---|
| [draw_detections](draw_detections.md) | Sibling overlay for boxes. |
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_segmentation` (lines 133-156)
