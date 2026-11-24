# read_single_slot_manifest

## Summary

Read the artifact manifest file named by a spec.

## Detailed Description

### Behavior

The function reads `<artifact_dir>/<spec.manifest_filename>` as JSON. It takes `context_len` and `repo_id` from the file. It sets `cache_batch` to 1.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def read_single_slot_manifest(artifact_dir: Path, spec: SingleSlotSpec) -> ArtifactManifest
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| artifact_dir | `Path` | none | Yes | Compiled artifact directory. |
| spec | `SingleSlotSpec` | none | Yes | Provides `manifest_filename`. |

## Returns

`ArtifactManifest`. `context_len` and `repo_id` come from the file. `cache_batch` is 1.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `FileNotFoundError` | The manifest file does not exist. | Check the artifact directory. |
| `KeyError` | The file has no `context_len`. | Rebuild the artifact. |
| `json.JSONDecodeError` | The file is not valid JSON. | Fix the file. |

## Usage Examples

### Basic

```python
from pathlib import Path
from axplugin import hf_adapter
artifact_dir = "/path/to/artifact"
d = Path(artifact_dir)
spec = hf_adapter.resolve_single_slot_spec(d)
print(hf_adapter.read_single_slot_manifest(d, spec))
```

## Edge Cases

- `repo_id` is `None` when the file has no `repo_id` key.

## Related APIs

| API | Relationship |
|---|---|
| [ArtifactManifest](ArtifactManifest.md) | Return type. |
| [read_manifest](read_manifest.md) | Wraps this function. |
| [SingleSlotSpec](SingleSlotSpec.md) | Argument type. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::read_single_slot_manifest` (lines 267-283)
