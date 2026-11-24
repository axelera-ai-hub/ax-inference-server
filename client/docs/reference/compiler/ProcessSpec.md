# ProcessSpec

## Overview

`ProcessSpec` is a dataclass that describes how to launch one compiled pipeline server process. `PipelineCompiler.compile_all` returns one per pipeline.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| pipeline_id | str | Pipeline id from the config. |
| port | int | Port the pipeline's server listens on. |
| pipeline_json_path | str | Path of the generated pipeline JSON file. |
| taskset_cpus | Optional[str] | CPU list for pinning, or `None` for no pinning. |
| membind | Optional[int] | NUMA node for memory binding, or `None`. |
| env | dict[str, str] | Extra environment variables for the process: `AXELERA_FRAMEWORK` and `GRPC_OUTPUT_FORMAT`. |

## Methods

This class has no methods.

## Initialization

```python
ProcessSpec(pipeline_id: str, port: int, pipeline_json_path: str, taskset_cpus: Optional[str], membind: Optional[int], env: dict[str, str])
```

All fields are required.

## Lifecycle

`PipelineCompiler.compile_all` creates the instances. `client/ui/gui/pipeline_compile.py` reads `pipeline_id`, `port`, `pipeline_json_path`, `taskset_cpus` and `membind` from each spec. `client/examples/helper/deploy.py` writes the same five fields to `manifest.json`. Neither consumer reads `env`.

## Related Classes

| Class | Relationship |
|---|---|
| [PipelineCompiler](PipelineCompiler.md) | Produces the specs. |
| [PipelineConfig](../configs/PipelineConfig.md) | Source of `port`, `taskset_cpus` and `membind`. |

## Source Reference

- `client/compiler/pipeline.py::ProcessSpec` (lines 28-46)
