# python -m helper models provision

## Summary

Downloads and compiles prebuilt models on a device.

## Detailed Description

### Behavior

For each name, the command calls `server.provision_model(name, device, meta_key)`. The device is `--device`, or the first healthy device when `--device` is not given. Each model compiles for 3 AIPU cores without OpenCL. The first run can take several minutes per model.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper models provision NAME [NAME ...] [--device INDEX] [--meta-key KEY]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | The literal `provision`. |
| names | str (one or more) | none | Yes | Prebuilt model names such as `yolox-m-coco-onnx`. |
| --device | int | first healthy device | No | Device to compile on. |
| --meta-key | str | none | No | Postprocess `meta_key` to patch into the `.axnet` of every named model. |

## Returns

Stdout is empty. Progress goes to stderr. Exit code 0 when every model is provisioned.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The download, compile or patch request fails, or no device is healthy. | Read the error text and retry. |
| 2 | No model name is given, or the environment is not set. | Pass at least one name from `models list`. |

## Usage Examples

### Basic

```bash
python -m helper models provision yolox-m-coco-onnx --meta-key detections
```

## Edge Cases

- The first failing model stops the command. Earlier models stay provisioned.
- `--meta-key` applies to every name in the call.

## Related APIs

| API | Relationship |
|---|---|
| [server.provision_model](server.provision_model.md) | Provisions one model. |
| [cli-models-list](cli-models-list.md) | Lists valid names. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_models` (lines 47-61)
- `client/examples/helper/__main__.py::main` (lines 326-347)
