"""Single-request generation loop over a loaded Axelera model.

Provides SingleSlotAdapter, which prefills and decodes one sequence at a time, and sample_next_token().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import torch


def sample_next_token(logits: np.ndarray, temperature: float) -> int:

    """Pick the next token id from a logits vector.

    Args:
        logits (np.ndarray): Logits for the last position; flattened to 1-D.
        temperature (float): 0 selects the argmax; otherwise logits are divided by it and sampled from the softmax.

    Returns:
        int: The chosen token id.
    """
    logits = np.asarray(logits).astype(np.float32).reshape(-1)
    if temperature == 0:
        return int(np.argmax(logits))
    scaled = logits / temperature
    probs = np.exp(scaled - scaled.max())
    probs /= probs.sum()
    return int(np.random.choice(len(probs), p=probs))


@dataclass
class SingleSlotRequest:
    """Result of admitting a request.

    Attributes:
        slot (int): Batch slot of the request; always 0.
        tokens (list[int]): Tokens produced so far (the first generated token on admission).
    """
    slot: int
    tokens: list[int]


BuildInputs = Callable[[Any, Any, "list[object] | None"], dict[str, Any]]


class SingleSlotAdapter:
    """Drives a loaded model with one live request at a time.

    Admission runs the prefill and samples the first token; step() decodes one more token per call until an EOS token or the token budget ends the request.

    Note:
        Not thread-safe and not batched: admit() raises while a request is live.
    """

    def __init__(self, model: Any, *, build_inputs: BuildInputs) -> None:
        """Wrap a model.

        Args:
            model (Any): Model exposing forward(), optionally generation_config, _position and release().
            build_inputs (BuildInputs): Builds forward() inputs from (model, prompt data, images).
        """
        self._model = model
        self._build_inputs = build_inputs
        self._eos_ids = self._collect_eos_ids(model)
        self._max_new_tokens = 0
        self._temperature = 0.0
        self._live = False
        self._last_token = 0
        self._generated = 0

    @staticmethod
    def _collect_eos_ids(model: Any) -> set[int]:
        """Return the EOS token ids from the model's generation_config, as a set (empty if none)."""
        eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
        if eos is None:
            return set()
        if isinstance(eos, int):
            return {eos}
        return {int(e) for e in eos}

    def start_batch(self, *, max_new_tokens: int = 128, temperature: float = 0.0) -> None:
        """Set the default token budget and sampling temperature.

        Args:
            max_new_tokens (int, optional): Default budget per request. Defaults to 128.
            temperature (float, optional): Sampling temperature for all requests. Defaults to 0.0.
        """
        self._max_new_tokens = max_new_tokens
        self._temperature = temperature

    def admit(
        self,
        prompt_data: Any,
        images: "list[object] | None" = None,
        *,
        max_new_tokens: int | None = None,
    ) -> SingleSlotRequest:
        """Run the prefill for a request and sample its first token.

        Resets the model's _position cursor if it has one. The request budget is max_new_tokens if truthy, otherwise the current default; the budget replaces the stored default.

        Args:
            prompt_data (Any): Prompt token ids or chat messages, as understood by build_inputs.
            images (list[object] | None, optional): Images for the request. Defaults to None.
            max_new_tokens (int | None, optional): Token budget including the first token. Defaults to None.

        Returns:
            SingleSlotRequest: Slot 0 with the first generated token.

        Raises:
            RuntimeError: If a previous request is still live.
        """
        if self._live:
            raise RuntimeError(
                "SingleSlotAdapter.admit() called while a request is still live -- "
                "AxeleraPlatform should have capped max_num_seqs to 1 for this artifact"
            )
        if hasattr(self._model, "_position"):
            self._model._position = 0
        inputs = self._build_inputs(self._model, prompt_data, images)
        budget = max_new_tokens or self._max_new_tokens
        with torch.inference_mode():
            out = self._model.forward(**inputs, cache_position=None, logits_to_keep=1)
        token = sample_next_token(out.logits[0, -1].numpy(), self._temperature)
        self._max_new_tokens = budget
        self._generated = 1
        self._last_token = token
        self._live = token not in self._eos_ids and self._generated < self._max_new_tokens
        return SingleSlotRequest(slot=0, tokens=[token])

    def step(self) -> dict[int, int]:
        """Decode one token for the live request.

        Returns:
            dict[int, int]: {0: token}, or {} if no request is live.
        """
        if not self._live:
            return {}
        with torch.inference_mode():
            out = self._model.forward(
                input_ids=torch.tensor([[self._last_token]]),
                cache_position=torch.tensor([self._generated]),
                logits_to_keep=1,
            )
        token = sample_next_token(out.logits[0, -1].numpy(), self._temperature)
        self._generated += 1
        self._last_token = token
        self._live = token not in self._eos_ids and self._generated < self._max_new_tokens
        return {0: token}

    def release(self) -> None:
        """Call the model's release() method if it has one."""
        release = getattr(self._model, "release", None)
        if release is not None:
            release()
