# GlobalSettings

## Overview

`GlobalSettings` is the `global:` section of the server config. It holds the settings shared by every pipeline and instance. Some fields apply only to the `instances:` mode and others only to `pipelines:`. The Description column names the mode.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| axnet_model_path | Optional[str] | `None` | instances only | Required when `instances:` is non-empty | Path of the compiled `.axnet` model file. |
| sdk_root | str | `""` | yes (or `$SDK_ROOT`) | Non-blank after the environment fallback | Voyager SDK root. Taken from `$SDK_ROOT` when omitted. |
| grpc_output_format | Optional[str] | `None` | instances only | One of `BGR`, `RGBA` or `I420`. Required when `instances:` is non-empty | Output colour format for instances. Pipelines use `im_decode_output_format`. |
| use_axinference_net_opencl | Optional[str] | `None` | instances only | `--enable-opencl` or `--disable-opencl`. Required when `instances:` is non-empty | OpenCL flag for instances. |
| sdk_venv | str | `"venv"` | no | none | Name of the venv directory under `sdk_root`. |
| use_simd_decode | int | `1` | no | none | 0 selects the OpenCV decoder. 1 selects TurboJPEG SIMD. |
| restart_interval | int | `0` | no | none | Auto-restart interval in seconds. 0 disables it. |
| watchdog_timeout_ms | int | `0` | no | none | Watchdog restart threshold in ms. Pipelines only. 0 disables it. |
| timeout | int | `5` | no | none | Request timeout in seconds. Instances only. |
| flush_thres | int | `4850` | no | none | Flush threshold in ms. Instances only. |
| pipeline_depth | Optional[int] | `None` | no | none | Maximum in-flight frames. The compiler uses 13 when unset. |
| result_queue_depth | Optional[int] | `None` | no | none | Capacity of the shared result queue. Pipelines only. Unset lets the server derive it. |

## Validators

| Target | Rule |
|---|---|
| `grpc_output_format` | Must be `BGR`, `RGBA` or `I420` when set. |
| `use_axinference_net_opencl` | Must be `--enable-opencl` or `--disable-opencl` when set. |
| `sdk_root` | Before validation, an empty or missing value is filled from `$SDK_ROOT`. The result must not be blank. |

## Example

```yaml
global:
  sdk_root: ${SDK_ROOT}
  restart_interval: 0
  pipeline_depth: 13
```

## Related

| Page | Relationship |
|---|---|
| [ServerConfig](ServerConfig.md) | Holds this model as `global_settings`. |
| [InstanceConfig.to_env_vars](InstanceConfig.to_env_vars.md) | Reads these settings. |

## Source Reference

- `client/configs/utils/config_schema.py::GlobalSettings` (lines 37-123)
