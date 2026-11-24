# python -m helper up vision

## Summary

Compiles, uploads and launches a config in one step.

## Detailed Description

### Behavior

The command runs `deploy.compile_config`, `deploy.upload` and `deploy.launch` in order. It prints one `host:port` line per pipeline. The `kind` argument accepts only `vision`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper up vision CONFIG [--output-dir DIR]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| kind | str | none | Yes | The literal `vision`. |
| config | str | none | Yes | Path to the config YAML. |
| --output-dir | str | `compiled/<pipeline id>` | No | Output directory. |

## Returns

Stdout holds one `host:port` line per pipeline. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | The config is missing or rejected, or the environment is not set. | Fix the config. |

## Usage Examples

### Basic

```bash
python -m helper up vision configs/iso.yaml
```

## Edge Cases

- A failure stops the sequence at the failing step. Earlier steps are not undone.

## Related APIs

| API | Relationship |
|---|---|
| [cli-compile](cli-compile.md) | Compile step. |
| [cli-upload](cli-upload.md) | Upload step. |
| [cli-launch](cli-launch.md) | Launch step. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_up` (lines 125-131)
