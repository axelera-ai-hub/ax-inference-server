"""vLLM platform plugin for Axelera Metis.

Exposes AxeleraPlatform plus two process-wide patches it installs: no-op accelerator cache ops and chat-message passthrough in HfRenderer.
"""


from __future__ import annotations

from typing import TYPE_CHECKING

from vllm.logger import init_logger
from vllm.platforms.interface import Platform, PlatformEnum

if TYPE_CHECKING:
    from vllm.config import VllmConfig

logger = init_logger(__name__)


def disable_accelerator_cache_ops() -> None:

    """Replace torch.accelerator synchronize, empty_cache and empty_host_cache (if present) with no-ops.

    There is no accelerator device behind the CPU platform, so vLLM's calls to these functions must do nothing.
    """
    import torch

    def _noop(*args, **kwargs) -> None:
        """Accept any arguments and do nothing."""
        pass

    torch.accelerator.synchronize = _noop
    torch.accelerator.empty_cache = _noop
    if hasattr(torch.accelerator, "empty_host_cache"):
        torch.accelerator.empty_host_cache = _noop


_messages_passthrough_installed = False


def install_messages_passthrough_patch() -> None:

    """Patch HfRenderer so chat messages reach the multimodal processor.

    Wraps HfRenderer.render_messages and render_messages_async: when the prompt's multi_modal_data has "image" but no "messages", the conversation is added as mm_data["messages"]. Idempotent; installed once per process.
    """
    global _messages_passthrough_installed
    if _messages_passthrough_installed:
        return
    _messages_passthrough_installed = True

    from vllm.renderers.hf import HfRenderer

    def _inject_messages(conversation, prompt):
        """Add the conversation to the prompt's multimodal data when it has images and no messages; return (conversation, prompt)."""
        mm_data = prompt.get("multi_modal_data") if isinstance(prompt, dict) else None
        if mm_data is not None and "image" in mm_data and "messages" not in mm_data:
            mm_data["messages"] = conversation
        return conversation, prompt

    _orig_render_messages = HfRenderer.render_messages
    _orig_render_messages_async = HfRenderer.render_messages_async

    def render_messages(self, messages, params):
        """Call the original render_messages, then inject the messages."""
        return _inject_messages(*_orig_render_messages(self, messages, params))

    async def render_messages_async(self, messages, params):
        """Call the original render_messages_async, then inject the messages."""
        return _inject_messages(*(await _orig_render_messages_async(self, messages, params)))

    HfRenderer.render_messages = render_messages
    HfRenderer.render_messages_async = render_messages_async


class AxeleraPlatform(Platform):
    """vLLM out-of-tree platform for Axelera Metis artifacts.

    Presents itself as a CPU platform (device_type "cpu") and adjusts the vLLM config to what a compiled single-slot artifact supports.

    Attributes:
        device_name (str): "cpu".
        device_type (str): "cpu".
        dispatch_key (str): "CPU".
        simple_compile_backend (str): "eager".
    """
    _enum = PlatformEnum.OOT
    device_name: str = "cpu"
    device_type: str = "cpu"
    dispatch_key: str = "CPU"
    simple_compile_backend: str = "eager"

    @classmethod
    def check_and_update_config(cls, vllm_config: VllmConfig) -> None:
        """Adapt the vLLM config to the compiled artifact.

        Installs the cache-op and messages patches, forces the "spawn" worker start method, selects AxeleraWorker if the worker class is "auto", forces eager mode, and disables chunked prefill, prefix caching, the multimodal processor cache and async scheduling. max_num_seqs is capped to the manifest cache_batch, max_model_len to its context_len, and max_num_batched_tokens is raised to at least context_len.

        Args:
            vllm_config (VllmConfig): Configuration modified in place.

        Raises:
            NotImplementedError: If world_size > 1 (one device per engine; use data parallelism).
        """
        import os

        disable_accelerator_cache_ops()
        install_messages_passthrough_patch()

        os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"

        parallel_config = vllm_config.parallel_config
        if parallel_config.worker_cls == "auto":
            parallel_config.worker_cls = "axplugin.worker.AxeleraWorker"

        if parallel_config.world_size > 1:
            raise NotImplementedError(
                "tensor/pipeline parallelism is not supported: a Metis artifact "
                "runs on one device per engine. Scale out with "
                "--data-parallel-size (one engine per device) instead."
            )

        vllm_config.model_config.enforce_eager = True

        from axplugin import hf_adapter

        artifact_dir = hf_adapter.resolve_artifact_dir(vllm_config)
        manifest = hf_adapter.read_manifest(vllm_config)

        scheduler_config = vllm_config.scheduler_config
        if scheduler_config.max_num_seqs > manifest.cache_batch:
            logger.info(
                "Capping max_num_seqs %d -> compiled cache_batch %d",
                scheduler_config.max_num_seqs,
                manifest.cache_batch,
            )
            scheduler_config.max_num_seqs = manifest.cache_batch

        scheduler_config.enable_chunked_prefill = False
        vllm_config.cache_config.enable_prefix_caching = False

        if vllm_config.model_config.multimodal_config is not None:
            vllm_config.model_config.multimodal_config.mm_processor_cache_gb = 0

        scheduler_config.async_scheduling = False

        model_config = vllm_config.model_config
        if model_config.max_model_len > manifest.context_len:
            logger.info(
                "Capping max_model_len %d -> compiled context_len %d",
                model_config.max_model_len,
                manifest.context_len,
            )
            model_config.max_model_len = manifest.context_len

        if scheduler_config.max_num_batched_tokens < manifest.context_len:
            scheduler_config.max_num_batched_tokens = manifest.context_len

        logger.info(
            "AxeleraPlatform configured: artifact=%s, worker_cls=%s, "
            "mode=%s, max_num_seqs=%d, cache_batch=%d, "
            "data_parallel_size=%d, enforce_eager=True, context_len=%d",
            artifact_dir,
            parallel_config.worker_cls,
            "single-slot",
            scheduler_config.max_num_seqs,
            manifest.cache_batch,
            parallel_config.data_parallel_size,
            manifest.context_len,
        )

    @classmethod
    def import_kernels(cls) -> None:
        """Import the CPU platform kernels."""
        from vllm.platforms.cpu import CpuPlatform

        CpuPlatform.import_kernels()

    @classmethod
    def get_attn_backend_cls(cls, *args, **kwargs) -> str:
        """Always raise; the models are attention-free.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "AxeleraPlatform models are attention-free; vLLM should not request "
            "an attention backend. Attention runs inside the compiled Metis graph."
        )

    @classmethod
    def manual_seed_all(cls, seed: int) -> None:
        """Do nothing; there are no devices to seed."""
        pass

    @classmethod
    def is_async_output_supported(cls, enforce_eager: bool | None) -> bool:
        """Return False; async output is not supported."""
        return False

    @classmethod
    def inference_mode(cls):
        """Return a torch.inference_mode() context."""
        import torch

        return torch.inference_mode()
