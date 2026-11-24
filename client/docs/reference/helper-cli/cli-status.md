# python -m helper status

## Summary

Prints queue statistics of pipelines.

## Detailed Description

### Behavior

The command resolves ids like `down` and calls `deploy.status(ids, --wait)`. It prints one line per pipeline. The exit code is 0 only when every pipeline has fresh stats and reports healthy.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper status [DIRECTORY] [--ids a,b] [--wait SECONDS]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | No | Compiled directory holding `manifest.json`. |
| --ids | str | none | No | Comma-separated pipeline ids. |
| --wait | float | 0.0 | No | Seconds to wait for the first fresh stats line of each pipeline. |

## Returns

Stdout holds one line per pipeline. Exit code 0 when all are healthy, 1 otherwise.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | A pipeline has no fresh stats or is not healthy. | Wait longer with `--wait`, or inspect the pipeline. |
| 2 | No directory or ids are given, or the environment is not set. | Pass one of them. |

## Usage Examples

### Basic

```bash
python -m helper status compiled/iso-detect --wait 30
```

## Edge Cases

- Stats older than 10 seconds count as missing.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.status](deploy.status.md) | Collects the stats. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_status` (lines 140-146)
