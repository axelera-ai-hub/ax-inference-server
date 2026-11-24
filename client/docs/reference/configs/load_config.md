# load_config

## Summary

Loads and validates a server config YAML file.

## Detailed Description

### Behavior

The function checks that the file exists and parses it with `yaml.safe_load`. It expands environment variables such as `${SDK_ROOT}` in every string value, recursively. It validates the result as a `ServerConfig`.

### Concurrency

The function reads the file synchronously. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def load_config(path: Union[str, Path]) -> ServerConfig
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| path | Union[str, Path] | none | yes | Path of the YAML file. |

## Returns

`ServerConfig`. The validated configuration.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| FileNotFoundError | The file does not exist. | Check the path. |
| pydantic.ValidationError | The content does not satisfy the schema. | Fix the fields named in the error. |

## Usage Examples

### Basic

```python
import sys

sys.path.insert(0, 'client/configs/utils')

from config_schema import load_config

cfg = load_config('server.yaml')
print([p.id for p in cfg.pipelines])
```

## Edge Cases

- Expansion applies to the whole document before validation. An undefined variable stays as written.
- An empty YAML file passes `None` to validation and raises `ValidationError`.

## Related APIs

| API | Relationship |
|---|---|
| [ServerConfig](ServerConfig.md) | Return type. |
| [PipelineCompiler](../compiler/PipelineCompiler.md) | Consumes the result. |

## Source Reference

- `client/configs/utils/config_schema.py::load_config` (lines 769-790)
