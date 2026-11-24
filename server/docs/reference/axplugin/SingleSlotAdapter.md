# SingleSlotAdapter

## Overview

Drives a loaded model with one live request at a time. Admission runs the prefill and samples the first token. `step()` decodes one more token per call until an EOS token or the token budget ends the request.

## Attributes

This class has no public attributes.

## Methods

| Method | Summary | Page |
|---|---|---|
| `start_batch` | Set the default token budget and sampling temperature. | - |
| `admit` | Run the prefill and sample the first token. | [SingleSlotAdapter.admit](SingleSlotAdapter.admit.md) |
| `step` | Decode one token for the live request. Return `{0: token}`, or `{}` if none is live. | - |
| `release` | Call the model `release()` method if it has one. | - |

## Initialization

`SingleSlotAdapter(model, *, build_inputs)` wraps a model. The model exposes `forward()` and optionally `generation_config` and `release()`. `build_inputs` builds `forward()` inputs from `(model, prompt data, images)`. The adapter reads EOS ids from `generation_config.eos_token_id` (an int or a list).

## Lifecycle

`start_batch`, then `admit`, then `step` until it returns `{}`, then `release`. The class is not thread-safe and not batched.

## Related Classes

| API | Relationship |
|---|---|
| [SingleSlotRequest](SingleSlotRequest.md) | Return type of `admit`. |
| [sample_next_token](sample_next_token.md) | Samples each token. |
| [SingleSlotSpec](SingleSlotSpec.md) | Supplies `build_inputs`. |
| [load_single_slot_adapter](load_single_slot_adapter.md) | Creates the adapter. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Drives the adapter. |

## Source Reference

- `server/vllm/axelera/axplugin/single_slot.py::SingleSlotAdapter` (lines 50-159)
