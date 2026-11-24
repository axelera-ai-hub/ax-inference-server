# resolve_single_slot_spec

## Summary

Find the `SingleSlotSpec` for an artifact directory.

## Detailed Description

### Behavior

The function reads `model_type` from `<artifact_dir>/config.json`. It looks the value up in `SINGLE_SLOT_SPECS`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def resolve_single_slot_spec(artifact_dir: Path) -> SingleSlotSpec | None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| artifact_dir | `Path` | none | Yes | Compiled artifact directory. |

## Returns

`SingleSlotSpec | None`. The matching spec, or `None` if `config.json` is missing or the `model_type` is unknown.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `json.JSONDecodeError` | `config.json` exists but is not valid JSON. | Fix the file. |

## Usage Examples

### Basic

```python
from pathlib import Path
from axplugin import hf_adapter
artifact_dir = "/path/to/artifact"
spec = hf_adapter.resolve_single_slot_spec(Path(artifact_dir))
print(spec.architecture if spec else None)
```

## Edge Cases

- The function returns `None` when `config.json` has no `model_type`.

## Related APIs

| API | Relationship |
|---|---|
| [SINGLE_SLOT_SPECS](SINGLE_SLOT_SPECS.md) | Lookup table. |
| [SingleSlotSpec](SingleSlotSpec.md) | Return type. |
| [hf_overrides_for](hf_overrides_for.md) | Uses the same lookup. |
| [read_manifest](read_manifest.md) | Raises `ValueError` when this function returns `None`. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::resolve_single_slot_spec` (lines 176-185)
