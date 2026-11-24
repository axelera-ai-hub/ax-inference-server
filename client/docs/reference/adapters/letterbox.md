# letterbox

## Summary

Fits a frame inside a black canvas, centred, with the aspect ratio kept.

## Detailed Description

### Behavior

The function scales the frame by `min(width / w, height / h)` and centres it on a black `(height, width, 3)` canvas. It resizes with `cv2.INTER_AREA` when shrinking and `cv2.INTER_LINEAR` otherwise.

### Concurrency

This function is stateless and does not modify its input. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def letterbox(raw: np.ndarray, width: int, height: int) -> np.ndarray
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame. |
| width | int | none | yes | Canvas width in pixels. |
| height | int | none | yes | Canvas height in pixels. |

## Returns

`np.ndarray`. A new `uint8` image of shape `(height, width, 3)`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import letterbox

tile = letterbox(frame.raw, 640, 360)
```

## Edge Cases

- The function upscales small frames.
- The input frame is not modified.

## Related APIs

| API | Relationship |
|---|---|
| [cell_rects](cell_rects.md) | Provides the target rectangles. |
| [put_label](put_label.md) | Adds a caption to the result. |

## Source Reference

- `client/adapters/common/rendering.py::letterbox` (lines 432-444)
