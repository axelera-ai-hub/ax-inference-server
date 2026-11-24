# main

## Summary

Compiles a server YAML config from the command line.

## Detailed Description

### Behavior

The function loads the config with `load_config`, compiles it with `PipelineCompiler` and prints one `id<TAB>port<TAB>json_path` line per pipeline.

### Concurrency

The function is synchronous. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def main() -> None
```

## Parameters

This function takes no parameters.

## Returns

`None`. The function prints to standard output and exits with status 1 and a usage message unless exactly two arguments are given.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| SystemExit | The argument count is not two. | Pass `<config.yaml> <output_dir>`. |
| FileNotFoundError | The config file does not exist. | Check the path. |
| pydantic.ValidationError | The config fails validation. | Fix the reported fields. |

## Usage Examples

### Basic

```bash
python client/compiler/pipeline.py server.yaml out/
```

## Edge Cases

- The output directory is created if missing.

## Related APIs

| API | Relationship |
|---|---|
| [PipelineCompiler](PipelineCompiler.md) | Does the work. |
| [load_config](../configs/load_config.md) | Loads the YAML. |

## Source Reference

- `client/compiler/pipeline.py::main` (lines 272-285)
