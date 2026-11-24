# AxeleraWorker

## Overview

vLLM worker that runs on the CPU and delegates execution to `AxeleraModelRunner`. It subclasses vLLM `Worker`. `AxeleraPlatform` selects it when `worker_cls` is `auto`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `device` | `torch.device` | CPU device. `init_device` sets it. |
| `model_runner` | `AxeleraModelRunner` | The runner. `init_device` creates it. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `init_device` | Set up the CPU device, the distributed environment and the seed. Create the model runner. | - |
| `load_model` | Call `model_runner.load_model()`. The `load_dummy_weights` argument is ignored. | - |
| `determine_available_memory` | Return 0. | - |
| `initialize_from_config` | Do nothing. | - |
| `compile_or_warm_up_model` | Return zero `CompilationTimes`. | - |
| `execute_model` | Run one scheduler step on the model runner. | - |
| `sleep` | Log a warning and do nothing. | - |
| `wake_up` | Log a warning and do nothing. | - |
| `reset_mm_cache` | Do nothing. | - |
| `reset_encoder_cache` | Do nothing. | - |
| `shutdown` | Call `close()` on the model runner if one exists. | - |

## Initialization

vLLM creates the worker with its standard `Worker` arguments. `init_device` creates the runner.

## Lifecycle

`init_device`, then `load_model`, then `execute_model` for each step. `shutdown` releases the runner.

## Related Classes

| API | Relationship |
|---|---|
| [AxeleraModelRunner](AxeleraModelRunner.md) | Runner the worker creates. |
| [AxeleraPlatform](AxeleraPlatform.md) | Selects this worker. |

## Source Reference

- `server/vllm/axelera/axplugin/worker.py::AxeleraWorker` (lines 27-85)
