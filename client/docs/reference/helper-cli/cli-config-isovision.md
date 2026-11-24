# python -m helper config isovision

## Summary

Writes a config YAML for N independent single-detector pipelines.

## Detailed Description

### Behavior

The command calls `config.isovision(args)` and writes the YAML text to `--output`. Pipeline ports start at `--port` and increase by one. See [config.isovision](config.isovision.md) for the generated structure.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set. The command queries the server for device health.

## Signature

```bash
python -m helper config isovision -o PATH [--pipelines N] [--devices-per-pipeline N] [--model NAME] [--meta-key KEY] [--cores N] [--port PORT] [tuning options]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| --pipelines | int | 1 | No | Number of pipelines. |
| --devices-per-pipeline | int | 1 | No | Devices per pipeline. |
| --model | str | `yolox-m-coco-onnx` | No | Detector model name. |
| --meta-key | str | none | No | `meta_key_override` for the model. |
| --cores | int | 4 | No | AIPU cores per device (1-4). |
| --port | int | 50060 | No | Port of the first pipeline. |
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
| 1 | The device query fails or a device is unhealthy. | Check the device health and retry. |
| 2 | Fewer devices than pipelines x devices-per-pipeline, a requested device is not present, or the environment is not set. | Lower the counts or pass indexes the server reports. |

## Usage Examples

### Basic

```bash
python -m helper config isovision --pipelines 2 --pin -o configs/iso.yaml
```

## Edge Cases

- The command needs pipelines x devices-per-pipeline healthy devices.

## Related APIs

| API | Relationship |
|---|---|
| [config.isovision](config.isovision.md) | Builds the YAML. |
| [cli-compile](cli-compile.md) | Compiles the written config. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_config` (lines 97-103)
- `client/examples/helper/__main__.py::build_parser` (lines 214-323)
