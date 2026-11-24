# load_logo

## Summary

Loads an image with an alpha channel and scales it to a given width.

## Detailed Description

### Behavior

The function reads the file with `cv2.IMREAD_UNCHANGED`. It returns `None` unless the image has four channels. It scales the logo to `width` and keeps the aspect ratio with `cv2.INTER_AREA`.

### Concurrency

This function is stateless. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def load_logo(path: str, width: int) -> Optional[np.ndarray]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| path | str | none | yes | Path of an image with an alpha channel, for example PNG. |
| width | int | none | yes | Target width in pixels. Values below 1 are raised to 1. |

## Returns

`Optional[np.ndarray]`. A BGRA image, or `None` if the file cannot be read or has no alpha channel.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import load_logo

logo = load_logo('logo.png', 120)
```

## Edge Cases

- A missing file returns `None` without an exception.
- A JPEG or a grayscale image returns `None`.

## Related APIs

| API | Relationship |
|---|---|
| [overlay_logo](overlay_logo.md) | Blends the loaded logo onto a canvas. |

## Source Reference

- `client/adapters/common/rendering.py::load_logo` (lines 467-477)
