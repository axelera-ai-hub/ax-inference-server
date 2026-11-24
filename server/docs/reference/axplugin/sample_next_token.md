# sample_next_token

## Summary

Pick the next token id from a logits vector.

## Detailed Description

### Behavior

The function flattens the logits to 1-D `float32`. At temperature 0 it returns the argmax. Otherwise it divides the logits by the temperature, applies a softmax and draws one sample with `np.random.choice`.

### Concurrency

The function uses the global NumPy random state. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def sample_next_token(logits: np.ndarray, temperature: float) -> int
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| logits | `np.ndarray` | none | Yes | Logits for the last position. |
| temperature | `float` | none | Yes | 0 selects the argmax. Other values scale the logits. |

## Returns

`int`. The chosen token id.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
import numpy as np
from axplugin.single_slot import sample_next_token
print(sample_next_token(np.array([0.1, 2.0, 0.3]), 0.0))  # 1
```

## Edge Cases

- Only `temperature == 0` selects the argmax. A negative value takes the sampling path.
- Sampling uses the global NumPy random state.

## Related APIs

| API | Relationship |
|---|---|
| [SingleSlotAdapter](SingleSlotAdapter.md) | Calls this function in `admit` and `step`. |

## Source Reference

- `server/vllm/axelera/axplugin/single_slot.py::sample_next_token` (lines 15-32)
