# python -m helper compile

## Summary

Validates a config YAML and compiles it into pipeline specs.

## Detailed Description

### Behavior

The command calls `deploy.compile_config(config, --output-dir)` and prints the output directory. The directory holds the pipeline specs and `manifest.json`. Later commands read the manifest.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

The command calls the server only when `SDK_ROOT` is unset (`GET /sdk-root`) or a net sets `meta_key_override`. In those cases `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set and the server must be reachable.

## Signature

```bash
python -m helper compile CONFIG [--output-dir DIR]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| config | str | none | Yes | Path to the config YAML. |
| --output-dir | str | `compiled/<pipeline id>` | No | Output directory. |

## Returns

Stdout holds the output directory path. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | A server request fails, for example the `GET /sdk-root` call or the `meta_key` patch. | Check the server and retry. |
| 2 | The file is missing, the config is rejected, or the server is needed and the environment is not set. | Fix the path or the config. |

## Usage Examples

### Basic

```bash
python -m helper compile configs/iso.yaml
# compiled/iso-detect
```

## Edge Cases

- The default directory name comes from [deploy.doc_id_for](deploy.doc_id_for.md).
- The command patches `meta_key_override` on the server before compiling.
- A config without `meta_key_override` compiles without a server call when `SDK_ROOT` is set.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.compile_config](deploy.compile_config.md) | Performs the compile. |
| [cli-upload](cli-upload.md) | Next step. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_compile` (lines 106-109)
