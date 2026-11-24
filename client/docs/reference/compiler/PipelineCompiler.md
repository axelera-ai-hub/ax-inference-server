# PipelineCompiler

## Overview

`PipelineCompiler` compiles a [ServerConfig](../configs/ServerConfig.md) into one JSON spec per pipeline and one `ProcessSpec` per pipeline. It writes `pipeline_<index>.json` into the output directory. Expression predicates compile to shared libraries in the same directory. See the [compiler concept page](../../client/compiler.md).

## Attributes

This class exposes no public attributes. It stores the config and output directory privately.

## Methods

| Method | Summary | Page |
|---|---|---|
| `__init__(config, output_dir)` | Stores the config and creates the output directory. | This page |
| `compile_all()` | Compiles every pipeline in config order. | [PipelineCompiler.compile_all](PipelineCompiler.compile_all.md) |

## Initialization

```python
PipelineCompiler(config: ServerConfig, output_dir: Path)
```

| Parameter | Type | Description |
|---|---|---|
| config | ServerConfig | Validated server configuration. |
| output_dir | Path | Directory for generated JSON files and predicate libraries. The constructor creates it, with parents, if needed. |

## Lifecycle

1. Construct the compiler. The output directory is created.
2. Call `compile_all()`. It validates node types, builds each spec and writes the files.
3. Pass the returned `ProcessSpec` list to the launcher.

The pipeline JSON has these keys: `pipeline_id`, `entry`, `global`, `nets`, `predicates` and `nodes`. The `global` block holds `timeout_s`, `pipeline_depth` (13 when unset), `im_decode_output_format`, `restart_interval_s` and `watchdog_timeout_ms`. It adds `result_queue_depth`, `imdecode_threads`, `imdecode_queue_depth` and `imdecode_queue_timeout_ms` when configured. Each net entry has `axnet_path` and `axnet_config`. It adds `meta_key` (from `meta_key_override` or the `.axnet` postprocess options) and `role` (`keypoints` or `face`, from the decoder name) when detected. Predicates that are expressions become `{"type": "plugin", "so_path": ...}` entries. Other predicates are dumped from their config. For `fan_in` nodes, missing `num_branches`, `fanin_timeout_ms` (twice `flush_thres`) and `gather` (`union`) are filled in. A string `next` becomes a one-element list.

## Related Classes

| Class | Relationship |
|---|---|
| [ProcessSpec](ProcessSpec.md) | Result type. |
| [PredicateCompiler](PredicateCompiler.md) | Builds expression predicates. |
| [ServerConfig](../configs/ServerConfig.md) | Input. |
| [load_config](../configs/load_config.md) | Loads the input from YAML. |

## Source Reference

- `client/compiler/pipeline.py::PipelineCompiler` (lines 93-269)
