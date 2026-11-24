# AxPassthroughDummyInputsBuilder

## Overview

Dummy-input builder that produces an empty prompt and no multimodal data. It subclasses `BaseDummyInputsBuilder[AxPassthroughProcessingInfo]`.

## Attributes

This class has no public attributes.

## Methods

| Method | Summary | Page |
|---|---|---|
| `get_dummy_text` | Return an empty string. | - |
| `get_dummy_mm_data` | Return an empty dict. | - |

## Initialization

Behavior inferred from code inspection.

## Lifecycle

Behavior inferred from code inspection.

## Related Classes

| API | Relationship |
|---|---|
| [AxPassthroughProcessingInfo](AxPassthroughProcessingInfo.md) | Info type of this builder. |
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Sibling processor. |
| [AxSingleSlotVisionModel](AxSingleSlotVisionModel.md) | Registers this class. |

## Source Reference

- `server/vllm/axelera/axplugin/multimodal.py::AxPassthroughDummyInputsBuilder` (lines 91-105)
