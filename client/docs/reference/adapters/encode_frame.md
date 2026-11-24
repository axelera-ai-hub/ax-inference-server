# encode_frame

## Summary

Encodes a frame as WebP or JPEG bytes.

## Detailed Description

### Behavior

The function selects WebP when `fmt == 'webp'`. Any other value selects JPEG. It passes `quality` to the matching OpenCV quality flag.

### Concurrency

This function is stateless and does not modify its input. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def encode_frame(raw: np.ndarray, fmt: str, quality: int) -> bytes
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame. |
| fmt | str | none | yes | `'webp'` for WebP. Any other value selects JPEG. |
| quality | int | none | yes | Encoder quality passed to OpenCV. |

## Returns

`bytes`. The encoded image.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| RuntimeError | `cv2.imencode` reports failure. | Check the frame is a valid non-empty image. |

## Usage Examples

### Basic

```python
from adapters.common.rendering import encode_frame

data = encode_frame(frame.raw, 'webp', 80)
```

## Edge Cases

- An unknown `fmt` such as `'png'` produces JPEG without an error.

## Related APIs

| API | Relationship |
|---|---|
| [decode_frame](decode_frame.md) | Inverse operation. |

## Source Reference

- `client/adapters/common/rendering.py::encode_frame` (lines 281-300)
