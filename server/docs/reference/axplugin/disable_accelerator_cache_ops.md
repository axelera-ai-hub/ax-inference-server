# disable_accelerator_cache_ops

## Summary

Replace `torch.accelerator` cache functions with no-ops.

## Detailed Description

### Behavior

The function sets `torch.accelerator.synchronize` and `torch.accelerator.empty_cache` to a no-op. It also replaces `empty_host_cache` when the attribute exists. No device sits behind the CPU platform, so these calls must do nothing.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

The change is process-wide and has no undo.

## Signature

```python
def disable_accelerator_cache_ops() -> None
```

## Parameters

This function takes no parameters.

## Returns

`None`.

## Exceptions

None raised by this code.

## Edge Cases

- Calling it twice is harmless.

## Related APIs

| API | Relationship |
|---|---|
| [AxeleraPlatform](AxeleraPlatform.md) | Calls this function in `check_and_update_config`. |
| [install_messages_passthrough_patch](install_messages_passthrough_patch.md) | Second process-wide patch. |

## Source Reference

- `server/vllm/axelera/axplugin/platform.py::disable_accelerator_cache_ops` (lines 20-35)
