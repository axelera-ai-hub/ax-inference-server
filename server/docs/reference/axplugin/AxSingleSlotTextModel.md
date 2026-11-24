# AxSingleSlotTextModel

## Overview

Registry marker for text-only single-slot Axelera models. It lets vLLM accept the model. It holds no weights and runs no computation. Inference runs in `SingleSlotAdapter`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `is_attention_free` | `bool` | `True`. The model needs no attention backend or KV cache. |
| `vllm_config` | `VllmConfig` | Config stored at construction. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `embed_input_ids` | Raises `NotImplementedError`. | - |
| `forward` | Raises `NotImplementedError`. | - |
| `compute_logits` | Raises `NotImplementedError`. | - |

## Initialization

`AxSingleSlotTextModel(vllm_config, prefix="")` stores `vllm_config`. The `prefix` argument is ignored. `AxeleraModelRunner.load_model` creates one instance.

## Lifecycle

The instance has no resources to release.

## Related Classes

| API | Relationship |
|---|---|
| [AxSingleSlotVisionModel](AxSingleSlotVisionModel.md) | Marker for image and text artifacts. |
| [SingleSlotAdapter](SingleSlotAdapter.md) | Runs the real inference. |
| [SingleSlotSpec](SingleSlotSpec.md) | Names this class in `marker_model_class` for `ax_causal_lm`. |

## Source Reference

- `server/vllm/axelera/axplugin/model.py::AxSingleSlotTextModel` (lines 31-57)
