# ServerConfig

## Overview

`ServerConfig` is the root of the server YAML config. It holds the global settings, named nets and predicates, graph pipelines and instances. At least one pipeline or instance is required.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| global_settings | GlobalSettings | none | yes | YAML key `global` | Global settings. |
| nets | dict[str, NetConfig] | `{}` | no | none | Named models. |
| predicates | dict[str, PredicateConfig] | `{}` | no | none | Named predicates. |
| pipelines | list[PipelineConfig] | `[]` | one of two | none | Graph pipelines. |
| instances | list[InstanceConfig] | `[]` | one of two | none | Single-net instances. |

## Validators

| Target | Rule |
|---|---|
| model | At least one of `instances` and `pipelines` must be non-empty. |
| instances | Ids must be 0..N-1. `axnet_model_path`, `use_axinference_net_opencl` and `grpc_output_format` must be set in `global`. |
| ports | No port may appear in more than one instance or pipeline. |
| net references | Every node `net` must name an entry of `nets`. |
| predicate references | Every `predicate`, `until` and `cases` key must name an entry of `predicates`. |

The model accepts the field name `global_settings` and the YAML key `global` (`populate_by_name`).

## Example

```yaml
global:
  sdk_root: ${SDK_ROOT}
nets:
  detector:
    axnet: ${SDK_ROOT}/build/yolo/yolo.axnet
    devices: [0]
pipelines:
  - id: detect
    port: 50051
    graph:
      entry: det
      nodes:
        - {id: det, type: net, net: detector, next: out}
        - {id: out, type: sink}
```

## Related

| Page | Relationship |
|---|---|
| [load_config](load_config.md) | Loads and validates this model from YAML. |
| [GlobalSettings](GlobalSettings.md) | The `global` section. |
| [PipelineConfig](PipelineConfig.md) | Element of `pipelines`. |
| [InstanceConfig](InstanceConfig.md) | Element of `instances`. |
| [NetConfig](NetConfig.md) | Value type of `nets`. |
| [PredicateConfig](PredicateConfig.md) | Value type of `predicates`. |

## Source Reference

- `client/configs/utils/config_schema.py::ServerConfig` (lines 663-755)
