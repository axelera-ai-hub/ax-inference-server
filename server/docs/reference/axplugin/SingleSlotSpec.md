# SingleSlotSpec

## Overview

Frozen dataclass that describes one supported single-slot model family. `SINGLE_SLOT_SPECS` holds one instance per `model_type`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `architecture` | `str` | Architecture name vLLM resolves the model to. |
| `auto_class` | `str` | Name of the transformers Auto class that loads the artifact. |
| `register_auto` | `Callable[[], None]` | Registers the model with the transformers Auto classes. |
| `manifest_filename` | `str` | Manifest file that holds `context_len` and `repo_id`. |
| `build_inputs` | `Callable` | Builds `forward()` inputs from `(model, prompt data, images)`. |
| `marker_model_class` | `str` | `module:Class` spec of the vLLM marker model. |

## Methods

This class has no public methods.

## Initialization

Construct it with keyword or positional fields in the order above. The module defines the two supported instances in `SINGLE_SLOT_SPECS`.

## Lifecycle

The instance is immutable.

## Related Classes

| API | Relationship |
|---|---|
| [SINGLE_SLOT_SPECS](SINGLE_SLOT_SPECS.md) | Table of instances. |
| [resolve_single_slot_spec](resolve_single_slot_spec.md) | Finds an instance. |
| [load_single_slot_adapter](load_single_slot_adapter.md) | Uses `register_auto`, `auto_class` and `build_inputs`. |
| [AxSingleSlotTextModel](AxSingleSlotTextModel.md) | Marker class of `ax_causal_lm`. |
| [AxSingleSlotVisionModel](AxSingleSlotVisionModel.md) | Marker class of `ax_smolvlm`. |

## Source Reference

- `server/vllm/axelera/axplugin/hf_adapter.py::SingleSlotSpec` (lines 123-141)
