# read_manifest

## Summary

Read the manifest of the artifact configured in a vLLM config.

## Detailed Description

### Behavior

The function resolves the artifact directory and its spec. It then calls `read_single_slot_manifest`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def read_manifest(vllm_config: VllmConfig) -> ArtifactManifest
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| vllm_config | `VllmConfig` | none | Yes | vLLM configuration. |

## Returns

`ArtifactManifest`. The artifact manifest.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ValueError` | No spec matches the artifact `model_type`. | Use an artifact with a known `model_type`. |
| `FileNotFoundError` | The manifest file does not exist. | Check the artifact directory. |

## Edge Cases

- The `ValueError` message includes the `model_type` and the known values.

## Related APIs

| API | Relationship |
|---|---|
| [resolve_artifact_dir](resolve_artifact_dir.md) | Locates the artifact. |
| [read_single_slot_manifest](read_single_slot_manifest.md) | Does the file read. |
| [AxeleraPlatform](AxeleraPlatform.md) | Calls this function in `check_and_update_config`. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::read_manifest` (lines 286-306)
