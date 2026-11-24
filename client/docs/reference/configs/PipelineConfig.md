# PipelineConfig

## Overview

`PipelineConfig` is one graph pipeline, an entry of `pipelines:`. Each pipeline runs in its own server process on its own port.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| id | str | none | yes | none | Pipeline identifier. |
| interface | Literal['grpc'] | `grpc` | no | Only `grpc` is allowed | Serving protocol. |
| port | int | none | yes | 1024-65535 | Port the pipeline server listens on. |
| taskset_cpus | str or None | `None` | no | none | CPU list. Applied with `numactl --physcpubind`, not the `taskset` binary. |
| membind | int or None | `None` | no | none | NUMA node for `numactl --membind`. Applied only when `taskset_cpus` is set. |
| im_decode_output_format | str | `BGR` | no | `BGR`, `RGBA` or `I420` | Colour format of decoded frames. |
| timeout | int | `5` | no | none | Per-request timeout in seconds. |
| flush_thres | int | `4850` | no | none | Flush threshold in ms. |
| imdecode_threads | int or None | `None` | no | none | Decode thread pool size override. |
| imdecode_queue_depth | int or None | `None` | no | none | Decode frame buffer capacity override. |
| imdecode_queue_timeout_ms | int or None | `None` | no | none | Decode queue backpressure timeout override in ms. |
| graph | PipelineGraphConfig | none | yes | none | The node graph. |

## Validators

| Target | Rule |
|---|---|
| `im_decode_output_format` | Must be `BGR`, `RGBA` or `I420`. |
| `port` | Must be within 1024-65535 (field constraint). |

## Example

```yaml
pipelines:
  - id: detect
    port: 50051
    im_decode_output_format: BGR
    graph:
      entry: det
      nodes:
        - {id: det, type: net, net: detector, next: out}
        - {id: out, type: sink}
```

## Related

| Page | Relationship |
|---|---|
| [PipelineGraphConfig](PipelineGraphConfig.md) | Type of `graph`. |
| [ServerConfig](ServerConfig.md) | Holds the `pipelines` list. |
| [PipelineCompiler](../compiler/PipelineCompiler.md) | Compiles each pipeline. |

## Source Reference

- `client/configs/utils/config_schema.py::PipelineConfig` (lines 586-660)
