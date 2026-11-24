# register_model

## Summary

Register the Axelera marker model classes with vLLM through the `vllm.general_plugins` entry point.

## Detailed Description

### Behavior

For every spec in `SINGLE_SLOT_SPECS`, the function calls `register_auto()`. It then calls `ModelRegistry.register_model` with the spec architecture and `marker_model_class`. It does nothing when `axelera.runtime` is not installed.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def register_model() -> None
```

## Parameters

This function takes no parameters.

## Returns

`None`.

## Exceptions

None raised by this code.

## Edge Cases

- `vllm` is imported only when the runtime is present.

## Related APIs

| API | Relationship |
|---|---|
| [register](register.md) | Platform entry point. |
| [SINGLE_SLOT_SPECS](SINGLE_SLOT_SPECS.md) | Table the function iterates. |
| [SingleSlotSpec](SingleSlotSpec.md) | Supplies `register_auto`, `architecture` and `marker_model_class`. |

## Source Reference

- `server/vllm/axelera/axplugin/__init__.py::register_model` (lines 28-44)
