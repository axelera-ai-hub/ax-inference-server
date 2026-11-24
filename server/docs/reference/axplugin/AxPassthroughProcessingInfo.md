# AxPassthroughProcessingInfo

## Overview

Processing info for models whose images and chat messages reach the runner unprocessed. It subclasses vLLM `BaseProcessingInfo`.

## Attributes

This class has no public attributes.

## Methods

| Method | Summary | Page |
|---|---|---|
| `get_supported_mm_limits` | Return `{"image": None, "messages": 1}`: unlimited images and one `messages` item. | - |
| `get_data_parser` | Return a parser that also understands the `messages` modality. | - |

## Initialization

Behavior inferred from code inspection. The class takes the `BaseProcessingInfo` constructor arguments.

## Lifecycle

Behavior inferred from code inspection.

## Related Classes

| API | Relationship |
|---|---|
| [AxPassthroughMultiModalProcessor](AxPassthroughMultiModalProcessor.md) | Processor that uses this info. |
| [AxPassthroughDummyInputsBuilder](AxPassthroughDummyInputsBuilder.md) | Builder typed on this info. |
| [AxSingleSlotVisionModel](AxSingleSlotVisionModel.md) | Registers this class. |

## Source Reference

- `server/vllm/axelera/axplugin/multimodal.py::AxPassthroughProcessingInfo` (lines 80-88)
