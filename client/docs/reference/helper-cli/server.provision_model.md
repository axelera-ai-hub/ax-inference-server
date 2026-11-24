# server.provision_model

## Summary

Downloads and compiles a prebuilt model, optionally patching its meta_key.

## Detailed Description

### Behavior

The function posts to `/prebuilt-models/download` with `opencl` false, `aipu_cores` 3, `force` false and `artifacts_only` false. The request waits up to 3600 seconds. With `meta_key`, it then posts to `/prebuilt-models/patch-meta-key`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The function compiles for 3 AIPU cores without OpenCL. The request timeout is 3600 seconds.

## Signature

```python
def provision_model(name: str, device: int, meta_key: str | None = None) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| name | str | none | Yes | Prebuilt model name. |
| device | int | none | Yes | Device to compile on. |
| meta_key | str \| None | `None` | No | Postprocess `meta_key` to patch into the `.axnet`. |

## Returns

`str`. The `axnet_path` from the server, or an empty string.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
path = server.provision_model("yolox-m-coco-onnx", 0, "detections")
```

## Edge Cases

- The first run can take several minutes.
- An existing model is reported as already present.

## Related APIs

| API | Relationship |
|---|---|
| [cli-models-provision](cli-models-provision.md) | Command wrapper. |
| [server.select_first_healthy](server.select_first_healthy.md) | Provides a device. |

## Source Reference

- `client/examples/helper/server.py::provision_model` (lines 203-223)
