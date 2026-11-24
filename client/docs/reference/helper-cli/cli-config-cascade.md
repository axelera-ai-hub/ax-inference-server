# python -m helper config cascade

## Summary

Writes a config YAML for a detector, filter and per-crop secondary pipeline.

## Detailed Description

### Behavior

The command calls `config.cascade(args, False)` and writes the YAML to `--output`. With `--devices auto` it prefers two devices and falls back to one. If the one-device fallback fails, the command exits with 1. With an explicit list, the command uses the first two listed devices.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper config cascade -o PATH [--detector NAME] [--secondary NAME] [--classes LIST] [--port PORT] [--pipeline-id ID] [core and meta-key options] [tuning options]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| --detector | str | `yolox-m-coco-onnx` | No | Detector model name. |
| --secondary | str | `yolo26npose-coco-onnx` | No | Secondary model name. |
| --detector-meta-key | str | `detections` | No | `meta_key` of the detector. |
| --secondary-meta-key | str | `keypoint_detections` | No | `meta_key` of the secondary model. |
| --secondary-meta-key-override | flag | off | No | Patch the secondary model to `--secondary-meta-key`. |
| --classes | str | `0` | No | Filter class indices to crop. An empty string keeps all classes. |
| --detector-cores | int | computed | No | AIPU cores of the detector stage. |
| --secondary-cores | int | computed | No | AIPU cores of the secondary stage. |
| --tertiary-cores | int | computed | No | AIPU cores of the tertiary stage. |
| --port | int | 50063 | No | gRPC port of the pipeline. |
| --pipeline-id | str | `cascade-demo` | No | Pipeline id. |
| --imdecode-threads | int | 4 | No | Image decode threads per pipeline. |
| --imdecode-queue-depth | int | 32 | No | Image decode queue depth. |
| --imdecode-queue-timeout-ms | int | 20000 | No | Image decode queue timeout in milliseconds. |
| --pin | flag | off | No | Add `taskset_cpus` and `membind` from the server NUMA plan. |
| --devices | str | `auto` | No | `auto` or a list such as `0,1,2`. |
| -o, --output | str | none | Yes | Config YAML path to write. Parent directories are created. |

## Returns

Stdout is empty. The command logs `wrote <path>` on stderr. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The device query fails, or no device or requested device is healthy (`ServerError`). | Check the device health and retry. |
| 2 | Cores are over-subscribed, a requested device is not present, or the environment is not set. | Pass explicit core options or an index the server reports. |

## Usage Examples

### Basic

```bash
python -m helper config cascade -o configs/cascade.yaml
```

## Edge Cases

- Without core options, a single device gives the detector 2 cores and the secondary 2 cores. Two devices give each 4 cores.

## Related APIs

| API | Relationship |
|---|---|
| [config.cascade](config.cascade.md) | Builds the YAML. |
| [cli-config-cascade3](cli-config-cascade3.md) | Adds a tertiary stage. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_config` (lines 97-103)
- `client/examples/helper/__main__.py::build_parser` (lines 214-323)
