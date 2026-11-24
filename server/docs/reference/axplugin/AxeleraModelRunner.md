# AxeleraModelRunner

## Overview

Minimal vLLM model runner for Axelera artifacts. It replaces vLLM's GPU runner. It loads the artifact through `hf_adapter` and generates through a `SingleSlotAdapter`. It has no KV cache.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `vllm_config` | `VllmConfig` | Config passed to the constructor. |
| `model_config` | `ModelConfig` | Taken from `vllm_config.model_config`. |
| `device` | `torch.device` | Device passed to the constructor. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `load_model` | Load the artifact onto its Metis device and create the executor. | [AxeleraModelRunner.load_model](AxeleraModelRunner.load_model.md) |
| `get_model` | Return the marker model. Raise `AssertionError` before `load_model`. | - |
| `get_kv_cache_spec` | Return an empty dict. | - |
| `get_supported_tasks` | Return `("generate",)`. | - |
| `execute_model` | Run one scheduler step. Raise `AssertionError` before `load_model`. | - |
| `close` | Release the adapter and drop the executor. | - |

## Initialization

`AxeleraModelRunner(vllm_config, device)` stores `vllm_config`, `model_config` and `device`. It loads nothing.

## Lifecycle

`load_model`, then `execute_model` per scheduler step, then `close`.

## Related Classes

| API | Relationship |
|---|---|
| [AxeleraWorker](AxeleraWorker.md) | Creates the runner. |
| [SingleSlotAdapter](SingleSlotAdapter.md) | Does the generation. |
| [load_single_slot_adapter](load_single_slot_adapter.md) | Loads the adapter. |
| [decode_messages](decode_messages.md) | Decodes the `messages` feature. |
| [decode_image](decode_image.md) | Decodes each image feature. |

## Source Reference

- `server/vllm/axelera/axplugin/model_runner.py::AxeleraModelRunner` (lines 157-261)
