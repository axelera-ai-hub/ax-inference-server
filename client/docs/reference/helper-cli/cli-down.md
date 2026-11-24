# python -m helper down

## Summary

Stops pipelines named by a compiled directory or by ids.

## Detailed Description

### Behavior

The command resolves ids with `deploy.pipeline_ids(directory, --ids)` and calls `deploy.down`. It logs `stopped` or `not running` per pipeline.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper down [DIRECTORY] [--ids a,b]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | No | Compiled directory holding `manifest.json`. |
| --ids | str | none | No | Comma-separated pipeline ids. Takes precedence over `directory`. |

## Returns

Stdout is empty. Exit code 0 even when a pipeline was not running.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | Neither `directory` nor `--ids` is given, or the manifest is missing. | Pass one of them. |

## Usage Examples

### Basic

```bash
python -m helper down --ids iso-detect,iso-detect-0
```

## Edge Cases

- A pipeline that the server did not start is reported as not running.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.down](deploy.down.md) | Stops each pipeline. |
| [deploy.pipeline_ids](deploy.pipeline_ids.md) | Resolves the ids. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_down` (lines 134-137)
