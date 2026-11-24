# SingleSlotAdapter.admit

## Summary

Run the prefill for a request and sample its first token.

## Detailed Description

### Behavior

The method calls `build_inputs`, runs `forward` with `logits_to_keep=1` under `torch.inference_mode()` and samples the first token. The request budget is `max_new_tokens` when truthy, otherwise the stored default. The budget then replaces the stored default. The request stays live unless the token is an EOS id or the budget is 1.

### Concurrency

The method is not thread-safe.

### Constraints

Call it only when no request is live.

## Signature

```python
def admit(self, prompt_data: Any, images: list[object] | None = None, *, max_new_tokens: int | None = None) -> SingleSlotRequest
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| prompt_data | `Any` | none | Yes | Prompt token ids or chat messages, as `build_inputs` understands them. |
| images | `Optional[list[object]]` | `None` | No | Images for the request. |
| max_new_tokens | `Optional[int]` | `None` | No | Token budget including the first token. Keyword only. |

## Returns

`SingleSlotRequest`. Slot 0 with the first generated token.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | A previous request is still live. | Drain the request with `step()` first. |
| `ValueError` | `build_inputs` rejects the input, for example images for a text-only model. | Fix the request. |

## Edge Cases

- `max_new_tokens=0` uses the stored default.
- A first token in the EOS set ends the request at admission.

## Related APIs

| API | Relationship |
|---|---|
| [SingleSlotAdapter](SingleSlotAdapter.md) | Owning class. |
| [SingleSlotRequest](SingleSlotRequest.md) | Return type. |
| [sample_next_token](sample_next_token.md) | Samples the first token. |

## Source Reference

- `server/vllm/axelera/axplugin/single_slot.py::SingleSlotAdapter.admit` (lines 95-133)
