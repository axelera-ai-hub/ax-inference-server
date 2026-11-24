# AxPassthroughMultiModalProcessor

## Overview

Multimodal processor that forwards images and chat messages to the runner. It runs no model-specific HF processor. It subclasses `BaseMultiModalProcessor[AxPassthroughProcessingInfo]`.

## Attributes

This class has no public attributes.

## Methods

This class has no public methods of its own. It overrides three hooks of `BaseMultiModalProcessor`.
It tokenizes the prompt without special tokens and encodes `images` with `encode_image`.
It batches `images` per image and shares `messages` with batch size 1.
It replaces each image token with itself and inserts one pad token at the prompt start for `messages`.
Neither update is embedded.

## Initialization

`AxSingleSlotVisionModel` registers it.

## Lifecycle

Behavior inferred from code inspection: the instance lives as long as the engine's processor.

## Related Classes

| API | Relationship |
|---|---|
| [AxPassthroughProcessingInfo](AxPassthroughProcessingInfo.md) | Info type. |
| [AxPassthroughDummyInputsBuilder](AxPassthroughDummyInputsBuilder.md) | Sibling builder. |
| [encode_image](encode_image.md) | Encodes the images. |
| [encode_messages](encode_messages.md) | Encodes the `messages` item. |
| [install_messages_passthrough_patch](install_messages_passthrough_patch.md) | Adds the `messages` item to the prompt. |

## Source Reference

- `server/vllm/axelera/axplugin/multimodal.py::AxPassthroughMultiModalProcessor` (lines 108-187)
