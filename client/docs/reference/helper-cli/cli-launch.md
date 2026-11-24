# python -m helper launch

## Summary

Launches the uploaded pipelines and prints their endpoints.

## Detailed Description

### Behavior

The command calls `deploy.launch(directory)` and prints one `host:port` line per pipeline. The host comes from `HOST_SERVER_URL`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper launch DIRECTORY
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | Yes | Output directory of `compile`, after `upload`. |

## Returns

Stdout holds one `host:port` line per pipeline. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | A spec is not uploaded, there is no manifest, or the environment is not set. | Run `compile` and `upload` first. |

## Usage Examples

### Basic

```bash
python -m helper launch compiled/iso-detect
# host:50060
```

## Edge Cases

- A launch request waits up to 200 seconds.
- A failure on a later pipeline leaves earlier pipelines running.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.launch](deploy.launch.md) | Performs the launch. |
| [cli-down](cli-down.md) | Stops pipelines. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_launch` (lines 118-122)
