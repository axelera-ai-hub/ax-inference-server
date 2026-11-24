# NetConfig

## Overview

`NetConfig` is a named model, an entry of `nets:`. Graph nodes of type `net` refer to it by name. You must give exactly one of `devices` and `axnet_config`.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| axnet | str | none | yes | none | Path of the compiled `.axnet` file. |
| devices | list[int] or None | `None` | one of two | Mutually exclusive with `axnet_config` | Device indices to run on. |
| cores | int | `4` | no | none | Cores per device when deriving `axnet_config`. |
| axnet_config | str or None | `None` | one of two | Matches `net-<name>;devices:<ids>-<cores>[;net-...]`. Mutually exclusive with `devices` | Raw axnet config string. Derived from `devices` when omitted. |
| labels_file | Optional[str] | `None` | no | Supports `${SDK_ROOT}` | Class labels file. The server uses the first non-`None` value across nets. |
| meta_key_override | Optional[str] | `None` | no | none | Replaces the net's default output meta key. Resolves key collisions between cascade nets. |

## Validators

| Target | Rule |
|---|---|
| model | Exactly one of `devices` and `axnet_config` must be set. When `devices` is set, `axnet_config` becomes `net-0;devices:<ids>-<cores>`. The final string must match the axnet config syntax. |

## Example

```yaml
nets:
  detector:
    axnet: ${SDK_ROOT}/build/yolo/yolo.axnet
    devices: [0]
    cores: 4
    meta_key_override: detections
```

## Related

| Page | Relationship |
|---|---|
| [GraphNodeConfig](GraphNodeConfig.md) | Nodes refer to a net through `net`. |
| [ServerConfig](ServerConfig.md) | Holds `nets`. |
| [PipelineCompiler](../compiler/PipelineCompiler.md) | Writes each referenced net to the pipeline JSON. |

## Source Reference

- `client/configs/utils/config_schema.py::NetConfig` (lines 272-330)
