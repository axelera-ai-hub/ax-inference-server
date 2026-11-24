# load_model_class

## Summary

Import the vLLM marker model class for the configured artifact.

## Detailed Description

### Behavior

The function resolves the artifact directory and its spec. It imports the class named by `spec.marker_model_class` (format `module:Class`).

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def load_model_class(vllm_config: VllmConfig) -> Any
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| vllm_config | `VllmConfig` | none | Yes | vLLM configuration. |

## Returns

`Any`. The marker model class, for example `AxSingleSlotTextModel`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ValueError` | No spec matches the artifact `model_type`. | Use an artifact with a known `model_type`. |

## Edge Cases

- The error message lists the known `model_type` values.

## Related APIs

| API | Relationship |
|---|---|
| [resolve_artifact_dir](resolve_artifact_dir.md) | Locates the artifact. |
| [resolve_single_slot_spec](resolve_single_slot_spec.md) | Finds the spec. |
| [AxSingleSlotTextModel](AxSingleSlotTextModel.md) | A possible result. |
| [AxSingleSlotVisionModel](AxSingleSlotVisionModel.md) | A possible result. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::load_model_class` (lines 231-250)
