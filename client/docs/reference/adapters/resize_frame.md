# resize_frame

## Summary

Downscales a frame to at most a given width and keeps the aspect ratio.

## Detailed Description

### Behavior

The function returns the input unchanged when `max_width_px <= 0` or the frame is not wider than the limit. Otherwise it returns a resized copy made with `cv2.INTER_AREA`. The new height is at least 1.

### Concurrency

This function is stateless and does not modify its input. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def resize_frame(raw: np.ndarray, max_width_px: int) -> np.ndarray
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame. |
| max_width_px | int | none | yes | Maximum width in pixels. Values of 0 or less disable resizing. |

## Returns

`np.ndarray`. The original frame when no resize is needed, otherwise a resized copy.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import resize_frame

small = resize_frame(frame.raw, 640)
```

## Edge Cases

- The function never upscales.
- The returned array can be the same object as the input.

## Related APIs

| API | Relationship |
|---|---|
| [resize_to_height](resize_to_height.md) | Same operation bounded by height. |
| [letterbox](letterbox.md) | Fits a frame into a fixed canvas instead. |

## Source Reference

- `client/adapters/common/rendering.py::resize_frame` (lines 236-253)
