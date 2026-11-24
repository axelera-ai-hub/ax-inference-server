# overlay_logo

## Summary

Alpha-blends a BGRA logo into the bottom-right corner of a canvas.

## Detailed Description

### Behavior

The function places the logo `margin` pixels from the right and bottom edges. It multiplies the logo alpha by `opacity` and blends it with the pixels beneath.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def overlay_logo(canvas: np.ndarray, logo: np.ndarray, margin: int, opacity: float = 0.85) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| canvas | np.ndarray | none | yes | BGR image, modified in place. |
| logo | np.ndarray | none | yes | BGRA image from `load_logo`. |
| margin | int | none | yes | Distance in pixels from the right and bottom edges. |
| opacity | float | `0.85` | no | Extra multiplier on the logo alpha. |

## Returns

`None`. The function draws onto `canvas`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import load_logo, overlay_logo

logo = load_logo('logo.png', 120)
if logo is not None:
    overlay_logo(canvas, logo, margin=16)
```

## Edge Cases

- The function does nothing if the logo plus margin does not fit.
- The function expects a 4-channel `logo`.

## Related APIs

| API | Relationship |
|---|---|
| [load_logo](load_logo.md) | Produces the `logo` argument. |

## Source Reference

- `client/adapters/common/rendering.py::overlay_logo` (lines 480-498)
