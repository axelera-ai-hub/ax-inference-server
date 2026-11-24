"""Marker model classes that register Axelera single-slot architectures with vLLM.

The classes only satisfy vLLM's model registry; their forward passes raise NotImplementedError because inference runs in axplugin.single_slot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

import torch
import torch.nn as nn
from vllm.multimodal import MULTIMODAL_REGISTRY

from axplugin.multimodal import (
    AxPassthroughDummyInputsBuilder,
    AxPassthroughMultiModalProcessor,
    AxPassthroughProcessingInfo,
)

if TYPE_CHECKING:
    from vllm.config import VllmConfig
    from vllm.multimodal.inputs import MultiModalEmbeddings

_SINGLE_SLOT_UNREACHABLE = (
    "{cls} is a registry marker only; inference runs on the Metis artifact via "
    "axplugin.single_slot.SingleSlotAdapter, driven by AxeleraModelRunner, "
    "not through this module's forward pass."
)


class AxSingleSlotTextModel(nn.Module):
    """Registry marker for text-only single-slot Axelera models.

    Registered with vLLM so it accepts the model, but it holds no weights and runs no computation: inference happens in SingleSlotAdapter, driven by AxeleraModelRunner.

    Attributes:
        is_attention_free (bool): True; the model needs no attention backend or KV cache.
    """

    is_attention_free: bool = True

    def __init__(self, vllm_config: VllmConfig, prefix: str = "") -> None:
        """Store the vLLM config."""
        super().__init__()
        self.vllm_config: VllmConfig = vllm_config

    def embed_input_ids(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))

    def forward(self, input_ids: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))

    def compute_logits(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))


@MULTIMODAL_REGISTRY.register_processor(
    AxPassthroughMultiModalProcessor,
    info=AxPassthroughProcessingInfo,
    dummy_inputs=AxPassthroughDummyInputsBuilder,
)
class AxSingleSlotVisionModel(nn.Module):
    """Registry marker for image-and-text single-slot Axelera models.

    Like AxSingleSlotTextModel it only lets vLLM accept the model. It is registered with the passthrough multimodal processor, which forwards raw images and chat messages to the runner, and it accepts image placeholders only.

    Attributes:
        supports_multimodal (bool): True.
        supports_multimodal_raw_input_only (bool): True; inputs reach the runner unprocessed.
        is_attention_free (bool): True; no attention backend or KV cache is needed.
    """

    supports_multimodal: ClassVar[Literal[True]] = True
    supports_multimodal_raw_input_only: ClassVar[bool] = True
    is_attention_free: bool = True

    def __init__(self, vllm_config: VllmConfig, prefix: str = "") -> None:
        """Store the vLLM config."""
        super().__init__()
        self.vllm_config: VllmConfig = vllm_config

    @classmethod
    def get_placeholder_str(cls, modality: str, i: int) -> str | None:
        """Return the prompt placeholder for a modality.

        Args:
            modality (str): Modality name; must start with "image".
            i (int): Index of the item (not used).

        Returns:
            str | None: "<image>".

        Raises:
            ValueError: If the modality is not an image modality.
        """
        if modality.startswith("image"):
            return "<image>"
        raise ValueError(f"Only image modality is supported, got {modality!r}")

    def embed_input_ids(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))

    def embed_multimodal(self, **kwargs: object) -> "MultiModalEmbeddings":
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))

    def forward(self, input_ids: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))

    def compute_logits(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Raise NotImplementedError: this marker model is never run."""
        raise NotImplementedError(_SINGLE_SLOT_UNREACHABLE.format(cls=type(self).__name__))
