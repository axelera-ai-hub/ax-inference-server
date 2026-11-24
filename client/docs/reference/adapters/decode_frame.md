# decode_frame

## Summary

Decodes encoded image bytes to a BGR array.

## Detailed Description

### Behavior

The function wraps `cv2.imdecode` with `cv2.IMREAD_COLOR`. It returns `None` when the bytes are not a decodable image. Empty bytes make OpenCV raise `cv2.error`.

### Concurrency

This function is stateless. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def decode_frame(data: bytes) -> Optional[np.ndarray]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| data | bytes | none | yes | Encoded image bytes, for example JPEG. |

## Returns

`Optional[np.ndarray]`. A BGR image, or `None` if the non-empty bytes cannot be decoded.

## Exceptions

| Exception | Trigger |
|---|---|
| `cv2.error` | `data` is empty. OpenCV fails the assertion `!buf.empty()`. |

## Usage Examples

### Basic

```python
from adapters.common.rendering import decode_frame

raw = decode_frame(jpeg_bytes)
if raw is None:
    raise ValueError('bad image')
```

## Edge Cases

- Corrupt data returns `None`.
- Empty data raises `cv2.error`.
- The result always has three colour channels.

## Related APIs

| API | Relationship |
|---|---|
| [encode_frame](encode_frame.md) | Inverse operation. |

## Source Reference

- `client/adapters/common/rendering.py::decode_frame` (lines 256-258)
