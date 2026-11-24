"""Multimodal passthrough for Axelera artifacts.

vLLM's multimodal pipeline is used only to carry raw images and chat messages to AxeleraModelRunner; no embeddings are computed here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import torch
from transformers import BatchFeature
from vllm.config.multimodal import BaseDummyOptions
from vllm.inputs import MultiModalDataDict
from vllm.multimodal.inputs import MultiModalFieldConfig
from vllm.multimodal.parse import ModalityDataItems, MultiModalDataParser
from vllm.multimodal.processing import (
    BaseDummyInputsBuilder,
    BaseMultiModalProcessor,
    BaseProcessingInfo,
    PromptIndexTargets,
    PromptInsertion,
    PromptReplacement,
    PromptUpdate,
    PromptUpdateDetails,
)

if TYPE_CHECKING:
    from vllm.multimodal.inputs import MultiModalKwargsItems
    from vllm.multimodal.parse import MultiModalDataItems as _MultiModalDataItems


class _MessagesItems(ModalityDataItems[Any, Any]):
    """Data items for the "messages" modality: the whole chat conversation as one item.

    It is passed through to the runner (see get_passthrough_data) rather than processed.
    """
    def __init__(self, data: Any) -> None:
        """Store the chat messages under the "messages" modality."""
        super().__init__(data, "messages")

    def get_count(self) -> int:
        """Return 1; the conversation is a single item."""
        return 1

    def get(self, index: int) -> Any:
        """Return the messages.

        Raises:
            IndexError: If index is not 0.
        """
        if index != 0:
            raise IndexError(index)
        return self.data

    def get_processor_data(self) -> Mapping[str, object]:
        """Return no data for the HF processor."""
        return {}

    def get_passthrough_data(self) -> Mapping[str, object]:
        """Return the messages encoded as a tensor under "messages" (see mm_wire.encode_messages)."""
        from axplugin import mm_wire

        return {"messages": mm_wire.encode_messages(self.data)}


class _AxPassthroughDataParser(MultiModalDataParser):
    """Multimodal data parser that adds a "messages" modality to the standard ones."""
    def _parse_messages_data(self, data: Any) -> ModalityDataItems[Any, Any] | None:
        """Wrap messages in _MessagesItems, or return None if data is None."""
        if data is None:
            return None
        return _MessagesItems(data)

    def _get_subparsers(self) -> Mapping[str, Any]:
        """Return the inherited subparsers plus the "messages" parser."""
        return {**super()._get_subparsers(), "messages": self._parse_messages_data}


class AxPassthroughProcessingInfo(BaseProcessingInfo):
    """Processing info for models whose images and chat messages are passed through to the runner unprocessed."""
    def get_supported_mm_limits(self) -> Mapping[str, int | None]:
        """Return the per-prompt limits: unlimited images and at most one "messages" item."""
        return {"image": None, "messages": 1}

    def get_data_parser(self) -> MultiModalDataParser:
        """Return the parser that also understands the "messages" modality."""
        return _AxPassthroughDataParser(expected_hidden_size=self._get_expected_hidden_size())


class AxPassthroughDummyInputsBuilder(BaseDummyInputsBuilder[AxPassthroughProcessingInfo]):

    """Dummy-input builder that produces an empty prompt and no multimodal data."""
    def get_dummy_text(self, mm_counts: Mapping[str, int]) -> str:
        """Return an empty dummy prompt."""
        return ""

    def get_dummy_mm_data(
        self,
        seq_len: int,
        mm_counts: Mapping[str, int],
        mm_options: Mapping[str, BaseDummyOptions],
    ) -> MultiModalDataDict:
        """Return no dummy multimodal data."""
        return {}


class AxPassthroughMultiModalProcessor(
    BaseMultiModalProcessor[AxPassthroughProcessingInfo]
):

    """Multimodal processor that forwards images and chat messages to the runner without running a model-specific HF processor.

    Images are converted to tensors, the chat messages ride along as a tensor, and prompt updates add placeholder tokens so vLLM's bookkeeping stays consistent.
    """
    def _call_hf_processor(
        self,
        prompt: str,
        mm_data: Mapping[str, object],
        mm_kwargs: Mapping[str, object],
        tok_kwargs: Mapping[str, object],
    ) -> BatchFeature:
        """Tokenize the prompt (no special tokens) and encode images as tensors.

        Args:
            prompt (str): Prompt text; an empty prompt gives empty input_ids.
            mm_data (Mapping[str, object]): Multimodal data; "images" entries are encoded with mm_wire.encode_image.
            mm_kwargs (Mapping[str, object]): Not used.
            tok_kwargs (Mapping[str, object]): Not used.

        Returns:
            BatchFeature: input_ids (one sequence) plus the multimodal data.
        """
        tokenizer = self.info.get_tokenizer()
        input_ids = tokenizer.encode(prompt, add_special_tokens=False) if prompt else []
        from axplugin import mm_wire

        images = mm_data.get("images")
        if images is not None:
            mm_data = {**mm_data, "images": [mm_wire.encode_image(image) for image in images]}
        return BatchFeature({"input_ids": [input_ids], **mm_data})

    def _get_mm_fields_config(
        self,
        hf_inputs: BatchFeature,
        hf_processor_mm_kwargs: Mapping[str, object],
    ) -> Mapping[str, MultiModalFieldConfig]:
        """Return the field layout: "images" batched per image, "messages" shared with batch size 1."""
        return {
            "images": MultiModalFieldConfig.batched("image"),
            "messages": MultiModalFieldConfig.shared("messages", batch_size=1),
        }

    def _get_prompt_updates(
        self,
        mm_items: "_MultiModalDataItems",
        hf_processor_mm_kwargs: Mapping[str, object],
        out_mm_kwargs: "MultiModalKwargsItems",
    ) -> Sequence[PromptUpdate]:
        """Return the prompt updates for images and messages.

        Each image token is replaced by itself and marked as not embedded. One pad token is inserted at the start of the prompt for the "messages" modality, also not embedded.
        """
        image_token_id = self.info.get_hf_config().image_token_id

        return [
            PromptReplacement(
                modality="image",
                target=[image_token_id],
                replacement=PromptUpdateDetails(
                    full=[image_token_id],
                    is_embed=lambda tokenizer, full: torch.zeros(
                        len(full), dtype=torch.bool
                    ),
                ),
            ),
            PromptInsertion(
                modality="messages",
                target=PromptIndexTargets.start(),
                insertion=PromptUpdateDetails(
                    full=[self.info.get_tokenizer().pad_token_id],
                    is_embed=lambda tokenizer, full: torch.zeros(
                        len(full), dtype=torch.bool
                    ),
                ),
            ),
        ]
