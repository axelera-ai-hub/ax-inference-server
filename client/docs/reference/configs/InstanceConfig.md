# InstanceConfig

## Overview

`InstanceConfig` is one single-net inference instance, an entry of `instances:`. Each instance gets its own gRPC port and axnet config string.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| id | int | none | yes | Ids across the config must form 0..N-1 | Instance index. |
| grpc_port | int | none | yes | 1024-65535 | Host port for the gRPC server. |
| grpc_axnet_config | str | none | yes | Matches `net-<name>;devices:<ids>-<cores>[;net-...]` | Axnet config string, for example `net-0;devices:0-4`. |
| taskset_cpus | Optional[str] | `None` | no | none | CPU list. Applied with `numactl --physcpubind`, not the `taskset` binary. |
| membind | Optional[int] | `None` | no | none | NUMA node for `numactl --membind`. Applied only when `taskset_cpus` is set. |

## Validators

| Target | Rule |
|---|---|
| `grpc_port` | Must be within 1024-65535. |
| `grpc_axnet_config` | Must match the axnet config syntax. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `to_env_vars(g)` | Builds the environment variables for the container. | [InstanceConfig.to_env_vars](InstanceConfig.to_env_vars.md) |

## Example

```yaml
instances:
  - id: 0
    grpc_port: 50051
    grpc_axnet_config: "net-0;devices:0-4"
```

## Related

| Page | Relationship |
|---|---|
| [InstanceConfig.to_env_vars](InstanceConfig.to_env_vars.md) | Builds the container environment. |
| [ServerConfig](ServerConfig.md) | Holds the `instances` list. |
| [GlobalSettings](GlobalSettings.md) | Supplies shared settings. |

## Source Reference

- `client/configs/utils/config_schema.py::InstanceConfig` (lines 126-202)
