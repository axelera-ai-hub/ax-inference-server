# config.axnet_path

## Summary

Returns the `${SDK_ROOT}`-relative path of the compiled `.axnet` of a model.

## Detailed Description

### Behavior

The function formats `${SDK_ROOT}/build/<model>/<model>.axnet`. It does not check that the file exists.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def axnet_path(model: str) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| model | str | none | Yes | Model name. |

## Returns

`str`. The path with the literal `${SDK_ROOT}` prefix.

## Exceptions

None.

## Usage Examples

### Basic

```python
from helper import config
print(config.axnet_path("yolox-m-coco-onnx"))
# ${SDK_ROOT}/build/yolox-m-coco-onnx/yolox-m-coco-onnx.axnet
```

## Edge Cases

- The result keeps `${SDK_ROOT}` unexpanded. The compiler resolves it.

## Related APIs

| API | Relationship |
|---|---|
| [config.isovision](config.isovision.md) | Uses the path for its net. |
| [config.cascade](config.cascade.md) | Uses the path for each stage. |

## Source Reference

- `client/examples/helper/config.py::axnet_path` (lines 22-24)
