"""Model runner that executes vLLM scheduler steps on a compiled Axelera artifact.

Exposes AxeleraModelRunner; request handling is delegated to a SingleSlotAdapter.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import torch.nn as nn
from vllm.logger import init_logger
from vllm.v1.outputs import EMPTY_MODEL_RUNNER_OUTPUT, ModelRunnerOutput

from axplugin import hf_adapter

if TYPE_CHECKING:
    import torch
    from vllm.config import VllmConfig
    from vllm.v1.core.sched.output import NewRequestData, SchedulerOutput
    from vllm.v1.kv_cache_interface import KVCacheSpec

logger = init_logger(__name__)


def _admission_payload(req: "NewRequestData") -> tuple[Any, list[object]]:

    """Extract the prompt data and images from a newly scheduled request.

    Decodes "messages" and "image" multimodal features (see axplugin.mm_wire), skipping features without data.

    Args:
        req (NewRequestData): The new request from the scheduler.

    Returns:
        tuple[Any, list[object]]: (decoded chat messages, or the prompt token ids if there are none; decoded images).
    """
    from axplugin import mm_wire

    messages = None
    images: list[object] = []
    for feature in req.mm_features:
        if feature.data is None:
            continue
        if feature.modality == "messages":
            messages = mm_wire.decode_messages(feature.data["messages"].data)
        elif feature.modality == "image":
            images.append(mm_wire.decode_image(feature.data["images"].data))
    if messages is not None:
        return messages, images
    return list(req.prompt_token_ids), images


class _TemperatureWarner:
    """Warns once if a request asks for a temperature different from the fixed one.

    The backend samples at the single temperature given at load time.
    """
    def __init__(self, temperature: float) -> None:
        """Store the fixed temperature."""
        self._temperature = temperature
        self._warned = False

    def warn_once(self, req_id: str, requested: float) -> None:
        """Log a warning on the first request whose temperature differs; later mismatches are silent.

        Args:
            req_id (str): Request id for the message.
            requested (float): Temperature the request asked for.
        """
        if self._warned or requested == self._temperature:
            return
        self._warned = True
        logger.warning(
            "request %s asked for temperature=%.3g, but this backend samples its "
            "whole batch at one fixed temperature=%.3g (set at model load); "
            "per-request temperature is not supported and is ignored (future "
            "requests will not be warned again).",
            req_id,
            requested,
            self._temperature,
        )


class _AdapterExecutor:

    """Translates vLLM scheduler output into SingleSlotAdapter calls.

    Tracks which adapter slot each request id occupies. Each execute() call yields one new token per running request.
    """
    def __init__(self, adapter: Any, *, max_new_tokens: int, temperature: float) -> None:
        """Start the adapter batch.

        Args:
            adapter (Any): SingleSlotAdapter-like object (start_batch, admit, step).
            max_new_tokens (int): Default token budget.
            temperature (float): Fixed sampling temperature.
        """
        self._adapter = adapter
        self._adapter.start_batch(max_new_tokens=max_new_tokens, temperature=temperature)
        self._temp_warner = _TemperatureWarner(temperature)
        self._slot_of_req: dict[str, int] = {}

    def execute(self, scheduler_output: "SchedulerOutput") -> ModelRunnerOutput:
        """Run one scheduler step.

        Running (cached) requests share one adapter.step() call, new requests are admitted (prefill plus first token), and finished requests are forgotten. Per-request temperature is ignored; a mismatch is warned about once.

        Args:
            scheduler_output (SchedulerOutput): The scheduler's work for this step.

        Returns:
            ModelRunnerOutput: Sampled tokens per request, in the order cached requests then new requests; EMPTY_MODEL_RUNNER_OUTPUT if nothing was scheduled.
        """
        if (
            scheduler_output.total_num_scheduled_tokens == 0
            and not scheduler_output.scheduled_new_reqs
        ):
            return EMPTY_MODEL_RUNNER_OUTPUT

        req_ids: list[str] = []
        req_id_to_index: dict[str, int] = {}
        sampled_token_ids: list[list[int]] = []

        cached = scheduler_output.scheduled_cached_reqs
        if cached.req_ids:
            produced = self._adapter.step()
            for req_id in cached.req_ids:
                slot = self._slot_of_req.get(req_id)
                token = produced.get(slot) if slot is not None else None
                req_id_to_index[req_id] = len(req_ids)
                req_ids.append(req_id)
                sampled_token_ids.append([token] if token is not None else [])

        for new_req in scheduler_output.scheduled_new_reqs:
            prompt_data, images = _admission_payload(new_req)
            sampling_params = new_req.sampling_params
            max_tokens = sampling_params.max_tokens if sampling_params is not None else None
            if sampling_params is not None:
                self._temp_warner.warn_once(new_req.req_id, sampling_params.temperature)
            request = self._adapter.admit(prompt_data, images or None, max_new_tokens=max_tokens)
            self._slot_of_req[new_req.req_id] = request.slot
            req_id_to_index[new_req.req_id] = len(req_ids)
            req_ids.append(new_req.req_id)
            sampled_token_ids.append([request.tokens[-1]])

        for req_id in scheduler_output.finished_req_ids:
            self._slot_of_req.pop(req_id, None)

        return ModelRunnerOutput(
            req_ids=req_ids,
            req_id_to_index=req_id_to_index,
            sampled_token_ids=sampled_token_ids,
        )


class AxeleraModelRunner:

    """Minimal vLLM model runner for Axelera artifacts.

    Replaces vLLM's GPU runner: it loads the artifact through hf_adapter and runs generation via _AdapterExecutor. It has no KV cache.
    """
    def __init__(self, vllm_config: "VllmConfig", device: "torch.device") -> None:
        """Store the config and device; nothing is loaded until load_model().

        Args:
            vllm_config (VllmConfig): vLLM configuration.
            device (torch.device): Device vLLM assigned to the worker.
        """
        self.vllm_config = vllm_config
        self.model_config = vllm_config.model_config
        self.device = device
        self._adapter = None
        self._model: nn.Module | None = None
        self._executor: _AdapterExecutor | None = None

    def _device_index(self) -> int:

        """Return the Metis device index for this engine.

        Uses the local data-parallel rank if set, otherwise the data-parallel index.
        """
        parallel_config = self.vllm_config.parallel_config
        local_rank = parallel_config.data_parallel_rank_local
        if local_rank is not None:
            return local_rank
        return parallel_config.data_parallel_index

    def load_model(self) -> None:
        """Load the artifact onto its Metis device and create the executor.

        The device is additional_config["device"] if given, else the data-parallel device index, and is exported as AXELERA_METIS_DEVICE. additional_config["temperature"] (default 0.0) is the fixed sampling temperature. The default token budget is max_model_len, or the manifest context_len if that is unset.
        """
        artifact_dir = hf_adapter.resolve_artifact_dir(self.vllm_config)
        manifest = hf_adapter.read_manifest(self.vllm_config)
        single_slot_spec = hf_adapter.resolve_single_slot_spec(artifact_dir)
        assert single_slot_spec is not None, "read_manifest() already rejects unknown artifacts"
        additional_config = self.vllm_config.additional_config or {}
        temperature = float(additional_config.get("temperature", 0.0))
        max_new_tokens = self.model_config.max_model_len or manifest.context_len

        device_override = additional_config.get("device")
        selected_device = device_override if device_override is not None else self._device_index()
        os.environ["AXELERA_METIS_DEVICE"] = str(selected_device)

        logger.info(
            "Loading Axelera single-slot artifact %s (model %s) on device %s",
            artifact_dir,
            self.model_config.model,
            selected_device,
        )
        adapter = hf_adapter.load_single_slot_adapter(
            single_slot_spec, artifact_dir, device=selected_device
        )

        self._adapter = adapter
        self._model = hf_adapter.load_model_class(self.vllm_config)(self.vllm_config)
        self._executor = _AdapterExecutor(
            adapter, max_new_tokens=max_new_tokens, temperature=temperature
        )
        logger.info(
            "Axelera runtime ready: mode=single-slot, cache_batch=%d, context_len=%d, "
            "device=%s, fixed temperature=%.3g",
            manifest.cache_batch,
            manifest.context_len,
            selected_device,
            temperature,
        )

    def get_model(self) -> nn.Module:
        """Return the marker model created by load_model().

        Raises:
            AssertionError: If load_model() has not been called.
        """
        assert self._model is not None, "load_model() must be called first"
        return self._model

    def get_kv_cache_spec(self) -> dict[str, "KVCacheSpec"]:
        """Return an empty spec; the model has no KV cache."""
        return {}

    def get_supported_tasks(self) -> tuple[str, ...]:
        """Return the supported tasks, only "generate"."""
        return ("generate",)

    def execute_model(self, scheduler_output: "SchedulerOutput") -> ModelRunnerOutput:
        """Run one scheduler step through the executor.

        Raises:
            AssertionError: If load_model() has not been called.
        """
        assert self._executor is not None, "load_model() must be called first"
        return self._executor.execute(scheduler_output)

    def close(self) -> None:
        """Release the adapter and drop the executor."""
        if self._adapter is not None:
            self._adapter.release()
            self._adapter = None
        self._executor = None
