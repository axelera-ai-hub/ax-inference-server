# hf_overrides_for

## Summary

Compute the vLLM `hf_overrides` for an artifact.

## Detailed Description

### Behavior

The function reads `<artifact_dir>/config.json`. It returns `{"architectures": [<architecture>]}` when `architectures` is empty or absent and `model_type` is in `SINGLE_SLOT_SPECS`. It returns `{}` in every other case. `serve.sh` passes the result to `--hf-overrides`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def hf_overrides_for(artifact_dir: Path) -> dict[str, Any]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| artifact_dir | `Path` | none | Yes | Compiled artifact directory. |

## Returns

`dict[str, Any]`. The overrides, or an empty dict.

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
print(hf_adapter.hf_overrides_for(Path(artifact_dir)))
```

## Edge Cases

- A missing `config.json` gives `{}`.
- An existing non-empty `architectures` list gives `{}`.

## Related APIs

| API | Relationship |
|---|---|
| [SINGLE_SLOT_SPECS](SINGLE_SLOT_SPECS.md) | Supplies the architecture name. |
| [serve.sh](serve.sh.md) | Calls this function. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::hf_overrides_for` (lines 188-207)
