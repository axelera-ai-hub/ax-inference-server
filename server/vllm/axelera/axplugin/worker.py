"""vLLM worker for the Axelera backend.

Exposes AxeleraWorker, selected by AxeleraPlatform as the default worker class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from vllm.logger import init_logger
from vllm.platforms import current_platform
from vllm.utils.torch_utils import set_random_seed
from vllm.v1.worker.gpu_worker import Worker, init_worker_distributed_environment
from vllm.v1.worker.worker_base import CompilationTimes

from axplugin.model_runner import AxeleraModelRunner

if TYPE_CHECKING:
    from vllm.v1.core.sched.output import SchedulerOutput
    from vllm.v1.kv_cache_interface import KVCacheConfig
    from vllm.v1.outputs import ModelRunnerOutput

logger = init_logger(__name__)


class AxeleraWorker(Worker):
    """vLLM worker that runs on the CPU and delegates execution to AxeleraModelRunner.

    Skips GPU memory profiling, KV cache setup, compilation and sleep mode, none of which apply to Metis artifacts.
    """

    def init_device(self) -> None:
        """Set up the CPU device, distributed environment and random seed, and create the model runner."""
        self.device = torch.device("cpu")
        init_worker_distributed_environment(
            self.vllm_config,
            self.rank,
            self.distributed_init_method,
            self.local_rank,
            current_platform.dist_backend,
        )
        set_random_seed(self.model_config.seed)
        self.model_runner = AxeleraModelRunner(self.vllm_config, self.device)

    def load_model(self, *, load_dummy_weights: bool = False) -> None:
        """Load the artifact through the model runner; load_dummy_weights is ignored."""
        self.model_runner.load_model()

    def determine_available_memory(self) -> int:
        """Return 0; there is no KV cache memory to profile."""
        return 0

    def initialize_from_config(self, kv_cache_config: "KVCacheConfig") -> None:
        """Do nothing; no KV cache is allocated."""
        pass

    def compile_or_warm_up_model(self) -> CompilationTimes:
        """Return zero compilation times; nothing is compiled or warmed up."""
        return CompilationTimes(language_model=0.0, encoder=0.0)

    def execute_model(self, scheduler_output: "SchedulerOutput") -> "ModelRunnerOutput":
        """Run one scheduler step on the model runner."""
        return self.model_runner.execute_model(scheduler_output)

    def sleep(self, level: int = 1) -> None:
        """Log a warning; sleep mode is not supported."""
        logger.warning("sleep mode is not supported on the Axelera backend, ignoring it.")

    def wake_up(self, tags: list[str] | None = None) -> None:
        """Log a warning; sleep mode is not supported."""
        logger.warning("sleep mode is not supported on the Axelera backend, ignoring it.")

    def reset_mm_cache(self) -> None:
        """Do nothing; there is no multimodal cache."""
        pass

    def reset_encoder_cache(self) -> None:
        """Do nothing; there is no encoder cache."""
        pass

    def shutdown(self) -> None:
        """Release the model runner if one was created."""
        if model_runner := getattr(self, "model_runner", None):
            model_runner.close()
