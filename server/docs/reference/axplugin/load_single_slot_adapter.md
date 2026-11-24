# load_single_slot_adapter

## Summary

Load an artifact through transformers and wrap it in a `SingleSlotAdapter`.

## Detailed Description

### Behavior

The function calls `spec.register_auto()`. It resolves `spec.auto_class` on the `transformers` module. It calls `from_pretrained(str(artifact_dir), device=device)` and wraps the model with `build_inputs=spec.build_inputs`.

### Concurrency

The adapter is not thread-safe.

### Constraints

None beyond the parameter types.

## Signature

```python
def load_single_slot_adapter(spec: SingleSlotSpec, artifact_dir: Path, *, device: Any) -> Any
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| spec | `SingleSlotSpec` | none | Yes | Spec of the artifact's model family. |
| artifact_dir | `Path` | none | Yes | Compiled artifact directory. |
| device | `Any` | none | Yes | Metis device selector passed to `from_pretrained`. Keyword only. |

## Returns

`SingleSlotAdapter`. The adapter around the loaded model.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ImportError` | `spec.register_auto()` cannot import its module. | Install the model package. |
| `AttributeError` | `transformers` has no class named `spec.auto_class`. | Fix the spec. |

## Edge Cases

- Errors from `from_pretrained` propagate unchanged.

## Related APIs

| API | Relationship |
|---|---|
| [SingleSlotSpec](SingleSlotSpec.md) | Argument type. |
| [SingleSlotAdapter](SingleSlotAdapter.md) | Return type. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Calls this function in `load_model`. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::load_single_slot_adapter` (lines 210-228)
