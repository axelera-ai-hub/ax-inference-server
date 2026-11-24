# encode_image

## Summary

Convert an image to a `uint8` tensor so it can pass through vLLM's multimodal pipeline.

## Detailed Description

### Behavior

The function converts an image that has a `convert` method to RGB. It converts the result to a `uint8` NumPy array and then to a tensor.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def encode_image(image: object) -> torch.Tensor
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| image | `object` | none | Yes | PIL-style image or array-like of `uint8` pixels. |

## Returns

`torch.Tensor`. `uint8` tensor of the pixel data (height x width x channels for RGB).

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from PIL import Image
from axplugin import mm_wire
t = mm_wire.encode_image(Image.new('RGB', (4, 2)))
print(t.shape, t.dtype)  # torch.Size([2, 4, 3]) torch.uint8
```

## Related APIs

| API | Relationship |
|---|---|
| [decode_image](decode_image.md) | Inverse. |
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Calls this function for each image. |

## Source Reference

- `server/vllm/axelera/axplugin/mm_wire.py::encode_image` (lines 14-26)
