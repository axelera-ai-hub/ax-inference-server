# encode_messages

## Summary

Serialize chat messages to JSON and return the UTF-8 bytes as a `uint8` tensor.

## Detailed Description

### Behavior

The function calls `json.dumps` on the messages and encodes the text as UTF-8. It wraps the bytes in a `uint8` tensor.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def encode_messages(messages: object) -> torch.Tensor
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| messages | `object` | none | Yes | JSON-serializable chat messages. |

## Returns

`torch.Tensor`. One-dimensional `uint8` tensor of the JSON bytes.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `TypeError` | The messages are not JSON-serializable. | Pass plain lists and dicts. |

## Usage Examples

### Basic

```python
from axplugin import mm_wire
t = mm_wire.encode_messages([{'role': 'user', 'content': 'hi'}])
print(mm_wire.decode_messages(t))
```

## Edge Cases

- An empty list encodes to the two bytes `[]`.

## Related APIs

| API | Relationship |
|---|---|
| [decode_messages](decode_messages.md) | Inverse. |
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Carries the tensor as the `messages` modality. |

## Source Reference

- `server/vllm/axelera/axplugin/mm_wire.py::encode_messages` (lines 34-41)
