# resize_to_height

## Summary

Downscales a frame to at most a given height and keeps the aspect ratio.

## Detailed Description

### Behavior

The function returns the input unchanged when `target_height_px <= 0` or the frame is not taller than the limit. Otherwise it returns a resized copy made with `cv2.INTER_AREA`. The new width is at least 1.

### Concurrency

This function is stateless and does not modify its input. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def resize_to_height(raw: np.ndarray, target_height_px: int) -> np.ndarray
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame. |
| target_height_px | int | none | yes | Maximum height in pixels. Values of 0 or less disable resizing. |

## Returns

`np.ndarray`. The original frame when no resize is needed, otherwise a resized copy.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import resize_to_height

thumb = resize_to_height(frame.raw, 360)
```

## Edge Cases

- The function never upscales.
- The returned array can be the same object as the input.

## Related APIs

| API | Relationship |
|---|---|
| [resize_frame](resize_frame.md) | Same operation bounded by width. |

## Source Reference

- `client/adapters/common/rendering.py::resize_to_height` (lines 261-278)
