# install_messages_passthrough_patch

## Summary

Patch `HfRenderer` so chat messages reach the multimodal processor.

## Detailed Description

### Behavior

The function wraps `HfRenderer.render_messages` and `HfRenderer.render_messages_async`. When the prompt `multi_modal_data` has `image` and no `messages`, the wrapper sets `mm_data["messages"]` to the conversation. The function installs once per process.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

The change is process-wide and has no undo. The function sets a module flag before it imports `vllm.renderers.hf`.

## Signature

```python
def install_messages_passthrough_patch() -> None
```

## Parameters

This function takes no parameters.

## Returns

`None`.

## Exceptions

None raised by this code.

## Edge Cases

- Later calls return at once.
- Prompts without `multi_modal_data` stay unchanged.

## Related APIs

| API | Relationship |
|---|---|
| [AxeleraPlatform](AxeleraPlatform.md) | Calls this function in `check_and_update_config`. |
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Consumes the `messages` item. |
| [disable_accelerator_cache_ops](disable_accelerator_cache_ops.md) | Second process-wide patch. |

## Source Reference

- `server/vllm/axelera/axplugin/platform.py::install_messages_passthrough_patch` (lines 41-73)
