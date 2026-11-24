# decode_messages

## Summary

Return the chat messages stored in a `uint8` tensor.

## Detailed Description

### Behavior

The function reads the tensor bytes, decodes them as UTF-8 and parses the JSON. It is the inverse of `encode_messages`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def decode_messages(tensor: torch.Tensor) -> object
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| tensor | `torch.Tensor` | none | Yes | Tensor made by `encode_messages`. |

## Returns

`object`. The decoded messages.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UnicodeDecodeError` | The bytes are not valid UTF-8. | Pass a tensor from `encode_messages`. |
| `json.JSONDecodeError` | The bytes are not valid JSON. | Pass a tensor from `encode_messages`. |

## Related APIs

| API | Relationship |
|---|---|
| [encode_messages](encode_messages.md) | Inverse. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Decodes the `messages` feature before admission. |

## Source Reference

- `server/vllm/axelera/axplugin/mm_wire.py::decode_messages` (lines 44-46)
