# AxeleraPlatform

## Overview

vLLM out-of-tree platform for Axelera Metis artifacts. It presents itself as a CPU platform and adjusts the vLLM config to what a compiled single-slot artifact supports.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| `device_name` | `str` | `"cpu"`. |
| `device_type` | `str` | `"cpu"`. |
| `dispatch_key` | `str` | `"CPU"`. |
| `simple_compile_backend` | `str` | `"eager"`. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `check_and_update_config` | Adapt the vLLM config to the artifact. | [AxeleraPlatform.check_and_update_config](AxeleraPlatform.check_and_update_config.md) |
| `import_kernels` | Call `CpuPlatform.import_kernels()`. | - |
| `get_attn_backend_cls` | Always raise `NotImplementedError`. | - |
| `manual_seed_all` | Do nothing. | - |
| `is_async_output_supported` | Return `False`. | - |
| `inference_mode` | Return a `torch.inference_mode()` context. | - |

## Initialization

vLLM loads the class through `register()`. All methods are class methods. No instance is needed.

## Lifecycle

The platform is stateless.

## Related Classes

| API | Relationship |
|---|---|
| [register](register.md) | Returns this class path. |
| [AxeleraWorker](AxeleraWorker.md) | Worker class the platform selects. |
| [disable_accelerator_cache_ops](disable_accelerator_cache_ops.md) | Installed by the platform. |
| [install_messages_passthrough_patch](install_messages_passthrough_patch.md) | Installed by the platform. |
| [ArtifactManifest](ArtifactManifest.md) | Source of the config caps. |

## Source Reference

- `server/vllm/axelera/axplugin/platform.py::AxeleraPlatform` (lines 76-206)
