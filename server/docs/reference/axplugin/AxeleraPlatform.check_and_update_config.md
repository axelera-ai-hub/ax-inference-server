# AxeleraPlatform.check_and_update_config

## Summary

Adapt the vLLM config to the compiled artifact.

## Detailed Description

### Behavior

The method installs both patches and sets `VLLM_WORKER_MULTIPROC_METHOD` to `spawn`. It selects `axplugin.worker.AxeleraWorker` when `worker_cls` is `auto`. It forces `enforce_eager`. It disables chunked prefill, prefix caching, the multimodal processor cache (`mm_processor_cache_gb = 0`) and async scheduling. It caps `max_num_seqs` to the manifest `cache_batch` and `max_model_len` to `context_len`. It raises `max_num_batched_tokens` to at least `context_len`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Tensor and pipeline parallelism are not supported.

## Signature

```python
@classmethod
def check_and_update_config(cls, vllm_config: VllmConfig) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| vllm_config | `VllmConfig` | none | Yes | Configuration modified in place. |

## Returns

`None`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `NotImplementedError` | `world_size` is greater than 1. | Use `--data-parallel-size`. |
| `ValueError` | No spec matches the artifact. | Use a supported artifact. |
| `FileNotFoundError` | The manifest file is missing. | Check the artifact. |

## Edge Cases

- The multimodal cache is changed only when `multimodal_config` is not `None`.
- The method logs a cap only for `max_num_seqs` and `max_model_len`.
- The method does not log the `max_num_batched_tokens` change.

## Related APIs

| API | Relationship |
|---|---|
| [AxeleraPlatform](AxeleraPlatform.md) | Owning class. |
| [read_manifest](read_manifest.md) | Supplies the caps. |
| [resolve_artifact_dir](resolve_artifact_dir.md) | Locates the artifact. |

## Source Reference

- `server/vllm/axelera/axplugin/platform.py::AxeleraPlatform.check_and_update_config` (lines 93-170)
