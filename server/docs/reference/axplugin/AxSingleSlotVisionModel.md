# AxSingleSlotVisionModel

## Overview

Registry marker for image-and-text single-slot Axelera models. It registers with the passthrough multimodal processor. It accepts image placeholders only.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `supports_multimodal` | `ClassVar[Literal[True]]` | `True`. |
| `supports_multimodal_raw_input_only` | `ClassVar[bool]` | `True`. Inputs reach the runner unprocessed. |
| `is_attention_free` | `bool` | `True`. No attention backend or KV cache. |
| `vllm_config` | `VllmConfig` | Config stored at construction. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `get_placeholder_str` | Return `"<image>"` for a modality that starts with `image`. Raise `ValueError` otherwise. | - |
| `embed_input_ids` | Raises `NotImplementedError`. | - |
| `embed_multimodal` | Raises `NotImplementedError`. | - |
| `forward` | Raises `NotImplementedError`. | - |
| `compute_logits` | Raises `NotImplementedError`. | - |

## Initialization

`AxSingleSlotVisionModel(vllm_config, prefix="")` stores `vllm_config`. The `prefix` argument is ignored. The class decorator registers `AxPassthroughMultiModalProcessor`, `AxPassthroughProcessingInfo` and `AxPassthroughDummyInputsBuilder` with `MULTIMODAL_REGISTRY`.

## Lifecycle

The instance has no resources to release.

## Related Classes

| API | Relationship |
|---|---|
| [AxSingleSlotTextModel](AxSingleSlotTextModel.md) | Text-only marker. |
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Registered processor. |
| [AxPassthroughProcessingInfo](AxPassthroughProcessingInfo.md) | Registered processing info. |
| [AxPassthroughDummyInputsBuilder](AxPassthroughDummyInputsBuilder.md) | Registered dummy inputs builder. |

## Source Reference

- `server/vllm/axelera/axplugin/model.py::AxSingleSlotVisionModel` (lines 60-117)
