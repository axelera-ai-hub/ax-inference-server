# InstanceConfig.to_env_vars

## Summary

Builds the environment variables passed to an instance's container.

## Detailed Description

### Behavior

The method combines the global settings and the instance fields. It always sets `GRPC_OUTPUT_FORMAT`, `USE_AXINFERENCE_NET_OPENCL`, `USE_SIMD_DECODE`, `AXNET_MODEL_PATH`, `SDK_ROOT`, `AXELERA_FRAMEWORK`, `restart_interval`, `timeout`, `flush_thres`, `grpc_port_0` and `grpc_axnet_config_0`. It adds `pipeline_depth`, `taskset_cpus_0` and `membind_0` only when set. `SDK_ROOT` and `AXELERA_FRAMEWORK` both hold `sdk_root`.

### Concurrency

The method has no side effects. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def to_env_vars(self, g: GlobalSettings) -> dict[str, str]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| g | GlobalSettings | none | yes | Global settings that supply format, SDK root, timeouts and decode options. |

## Returns

`dict[str, str]`. Variable name to string value.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
import sys

sys.path.insert(0, 'client/configs/utils')

from config_schema import load_config

cfg = load_config('server.yaml')
env = cfg.instances[0].to_env_vars(cfg.global_settings)
```

## Edge Cases

- An unset `use_axinference_net_opencl` or `axnet_model_path` becomes an empty string.
- An unset `grpc_output_format` is passed through as `None`, so the dictionary value is not a string. A config with `instances:` always sets it.

## Related APIs

| API | Relationship |
|---|---|
| [InstanceConfig](InstanceConfig.md) | Owning model. |
| [GlobalSettings](GlobalSettings.md) | Argument type. |

## Source Reference

- `client/configs/utils/config_schema.py::InstanceConfig.to_env_vars` (lines 173-202)
