# AxeleraModelRunner.load_model

## Summary

Load the artifact onto its Metis device and create the step executor.

## Detailed Description

### Behavior

The method resolves the artifact, manifest and spec. It reads `additional_config["temperature"]` (default 0.0). The device is `additional_config["device"]` when set, otherwise the local data-parallel rank, otherwise the data-parallel index. It exports the device as `AXELERA_METIS_DEVICE`. The default token budget is `max_model_len`, or the manifest `context_len` if that is unset. It creates the marker model with `load_model_class`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def load_model(self) -> None
```

## Parameters

This function takes no parameters.

## Returns

`None`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ValueError` | No spec matches the artifact. | Use a supported artifact. |
| `FileNotFoundError` | The manifest file is missing. | Check the artifact. |

## Edge Cases

- The process sets one temperature. A request with a different `SamplingParams.temperature` triggers one warning and the backend ignores it.

## Related APIs

| API | Relationship |
|---|---|
| [AxeleraModelRunner](AxeleraModelRunner.md) | Owning class. |
| [load_single_slot_adapter](load_single_slot_adapter.md) | Loads the adapter. |
| [read_manifest](read_manifest.md) | Reads the sizing. |
| [load_model_class](load_model_class.md) | Creates the marker class. |

## Source Reference

- `server/vllm/axelera/axplugin/model_runner.py::AxeleraModelRunner.load_model` (lines 189-228)
