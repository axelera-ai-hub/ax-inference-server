# PipelineCompiler.compile_all

## Summary

Compiles every pipeline in the config and returns the launch descriptions.

## Detailed Description

### Behavior

For each pipeline in config order, the method checks that every node type is supported. It builds the spec, writes `pipeline_<index>.json` into the output directory and builds a `ProcessSpec`. Referenced expression predicates compile to `predicate_<name>.cpp` and `.so` files in the same directory.

### Concurrency

The method is synchronous and writes files. Concurrency behavior depends on the underlying runtime.

### Constraints

Supported node types: net, filter, condition, switch, fan_out, fan_in, loop_guard, custom, sink, mock_net, roi_iter, roi_collect, rename.

## Signature

```python
def compile_all(self) -> list[ProcessSpec]
```

## Parameters

This function takes no parameters.

## Returns

`list[ProcessSpec]`. One entry per pipeline, in config order.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| NotImplementedError | A node type is outside the supported set. | Use a supported node type. |
| ValueError | An expression predicate is invalid. | Fix the `inputs` or `body` of the predicate. |
| RuntimeError | The C++ build of an expression predicate fails. | Read the stderr in the message and check the SDK include paths. |

## Usage Examples

### Basic

```python
import sys
from pathlib import Path

sys.path.insert(0, 'client/compiler')
sys.path.insert(0, 'client/configs/utils')

from config_schema import load_config
from pipeline import PipelineCompiler

cfg = load_config('server.yaml')
specs = PipelineCompiler(cfg, Path('out')).compile_all()
for s in specs:
    print(s.pipeline_id, s.port, s.pipeline_json_path)
```

## Edge Cases

- A config with an empty `pipelines` list returns an empty list.
- The method overwrites existing `pipeline_<index>.json` files.
- Files for earlier pipelines stay on disk when a later pipeline fails.

## Related APIs

| API | Relationship |
|---|---|
| [PipelineCompiler](PipelineCompiler.md) | Owning class. |
| [ProcessSpec](ProcessSpec.md) | Element type. |
| [main](main.md) | Command-line wrapper. |

## Source Reference

- `client/compiler/pipeline.py::PipelineCompiler.compile_all` (lines 111-120)
