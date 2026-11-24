# register

## Summary

Return the platform class path for vLLM's `vllm.platform_plugins` entry point.

## Detailed Description

### Behavior

The function checks whether `axelera.runtime` can be found without importing it. It returns the class path when the runtime exists. It returns `None` otherwise, so vLLM selects another platform.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def register() -> str | None
```

## Parameters

This function takes no parameters.

## Returns

`str | None`. The string `"axplugin.platform.AxeleraPlatform"`, or `None` if `axelera.runtime` is not installed.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from axplugin import register
print(register())
```

## Edge Cases

- A missing parent package for `axelera.runtime` counts as not installed.

## Related APIs

| API | Relationship |
|---|---|
| [register_model](register_model.md) | Second entry point of the plugin. |
| [AxeleraPlatform](AxeleraPlatform.md) | Class that the returned path names. |

## Source Reference

- `server/vllm/axelera/axplugin/__init__.py::register` (lines 16-25)
