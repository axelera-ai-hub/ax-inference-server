# SINGLE_SLOT_SPECS

## Overview

`SINGLE_SLOT_SPECS` is a module-level `dict[str, SingleSlotSpec]` in `hf_adapter`. The key is the `model_type` value of the artifact `config.json`. It is the single table that decides which artifacts the plugin supports.

## Fields

| Key (`model_type`) | `architecture` | `auto_class` | `manifest_filename` | `marker_model_class` | `build_inputs` behavior |
|---|---|---|---|---|---|
| `ax_causal_lm` | `AxQwen3SingleSlotForCausalLM` | `AutoModelForCausalLM` | `pipeline.json` | `axplugin.model:AxSingleSlotTextModel` | Builds `input_ids` and an all-ones `attention_mask`. Raises `ValueError` if images are given. |
| `ax_smolvlm` | `SmolVLMForConditionalGeneration` | `AutoModelForImageTextToText` | `vlm.json` | `axplugin.model:AxSingleSlotVisionModel` | Fills image items into the chat messages and applies the processor chat template. |

## Behavior

- With chat messages, the `ax_smolvlm` builder gives each `image` content item without an `image` key the next image, in order.
- With token ids and no images, the `ax_smolvlm` builder returns `input_ids` and an all-ones `attention_mask`.
- With token ids and images, the `ax_smolvlm` builder raises `ValueError`.
- `register_auto` for `ax_causal_lm` imports `model_axscript.llm.huggingface.register_auto`.
- `register_auto` for `ax_smolvlm` imports `model_axscript.llm.models.smolvlm2.hf_model.register_auto`.

## Example

```python
from axplugin.hf_adapter import SINGLE_SLOT_SPECS
print(sorted(SINGLE_SLOT_SPECS))  # ['ax_causal_lm', 'ax_smolvlm']
```

## Related

| API | Relationship |
|---|---|
| [SingleSlotSpec](SingleSlotSpec.md) | Value type. |
| [resolve_single_slot_spec](resolve_single_slot_spec.md) | Lookup function. |
| [hf_overrides_for](hf_overrides_for.md) | Uses the table. |
| [register_model](register_model.md) | Registers every marker class in the table. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::SINGLE_SLOT_SPECS` (lines 144-161)
