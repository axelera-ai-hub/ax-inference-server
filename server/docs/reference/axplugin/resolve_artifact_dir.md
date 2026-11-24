# resolve_artifact_dir

## Summary

Return the compiled artifact directory for a vLLM config.

## Detailed Description

### Behavior

The function reads `additional_config["artifact_dir"]`. It returns that path when set. Otherwise it returns `model_config.model` as a `Path`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def resolve_artifact_dir(vllm_config: VllmConfig) -> Path
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| vllm_config | `VllmConfig` | none | Yes | vLLM configuration. |

## Returns

`Path`. The artifact directory.

## Exceptions

None raised by this code.

## Edge Cases

- A `None` `additional_config` counts as empty.
- The function does not check that the directory exists.

## Related APIs

| API | Relationship |
|---|---|
| [load_model_class](load_model_class.md) | Calls this function. |
| [read_manifest](read_manifest.md) | Calls this function. |
| [AxeleraPlatform](AxeleraPlatform.md) | Calls this function in `check_and_update_config`. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::resolve_artifact_dir` (lines 309-322)
