# draw_detections

## Summary

Draws green bounding boxes with `label score` captions onto a frame.

## Detailed Description

### Behavior

For each detection the function draws a green rectangle and a filled caption box above it. The caption reads `label score` with two decimals. The function skips detections whose box has zero width or height.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_detections(raw: np.ndarray, detections) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| detections | iterable of detection messages | none | yes | Messages with `bbox` (fields `x`, `y`, `w`, `h`), `label` and `score`. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_detections

draw_detections(frame.raw, response.detections)
```

## Edge Cases

- A detection with `bbox.w == 0` or `bbox.h == 0` is skipped.
- The caption box is clamped to the top edge of the frame.

## Related APIs

| API | Relationship |
|---|---|
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_detections` (lines 23-44)
