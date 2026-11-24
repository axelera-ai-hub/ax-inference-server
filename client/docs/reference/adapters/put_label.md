# put_label

## Summary

Draws white text on a black background box.

## Detailed Description

### Behavior

The function measures the text with `cv2.FONT_HERSHEY_SIMPLEX` and draws a filled black box with padding. It then draws the white text inside the box. With `anchor='bottom-left'`, `y` is the bottom edge of the box.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def put_label(canvas: np.ndarray, text: str, x: int, y: int, scale: float = 0.6, anchor: str = 'top-left') -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| canvas | np.ndarray | none | yes | BGR image, modified in place. |
| text | str | none | yes | Label text. |
| x | int | none | yes | Left edge of the box. |
| y | int | none | yes | Top edge of the box, or its bottom edge when `anchor` is `'bottom-left'`. |
| scale | float | `0.6` | no | Font scale. |
| anchor | str | `'top-left'` | no | `'top-left'` or `'bottom-left'`. |

## Returns

`None`. The function draws onto `canvas`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import put_label

put_label(canvas, 'cam 0', 8, 8)
```

## Edge Cases

- Any `anchor` other than `'bottom-left'` behaves as `'top-left'`.
- OpenCV clips a box that extends past the canvas.

## Related APIs

| API | Relationship |
|---|---|
| [letterbox](letterbox.md) | Produces tiles that carry labels. |

## Source Reference

- `client/adapters/common/rendering.py::put_label` (lines 447-464)
