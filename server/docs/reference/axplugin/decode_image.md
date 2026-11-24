# decode_image

## Summary

Return an image tensor as a NumPy array.

## Detailed Description

### Behavior

The function calls `tensor.numpy()`. It is the inverse of `encode_image`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def decode_image(tensor: torch.Tensor) -> np.ndarray
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| tensor | `torch.Tensor` | none | Yes | Tensor made by `encode_image`. |

## Returns

`np.ndarray`. The pixel array.

## Exceptions

None raised by this code.

## Edge Cases

- The array shares memory with the tensor.

## Related APIs

| API | Relationship |
|---|---|
| [encode_image](encode_image.md) | Inverse. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Decodes each `image` feature before admission. |

## Source Reference

- `server/vllm/axelera/axplugin/mm_wire.py::decode_image` (lines 29-31)
