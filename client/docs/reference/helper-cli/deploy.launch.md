# deploy.launch

## Summary

Launches every uploaded pipeline and returns the endpoints.

## Detailed Description

### Behavior

For each manifest entry, the function posts to `/pipelines/launch` with the saved spec path, port, `taskset_cpus` and `membind`. Each request waits up to 200 seconds. The host comes from `HOST_SERVER_URL`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Every spec must be uploaded first. Each request waits up to 200 seconds.

## Signature

```python
def launch(directory: str) -> list[str]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | Yes | Output directory of `compile`, after `upload`. |

## Returns

`list[str]`. One `host:port` endpoint per pipeline.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | A spec has no `saved_path`, the manifest is missing, or the environment is unset. | Run `upload` first. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import deploy
for ep in deploy.launch("compiled/iso-detect"):
    print(ep)
```

## Edge Cases

- A failure on a later pipeline leaves earlier pipelines running.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.upload](deploy.upload.md) | Provides the saved paths. |
| [deploy.down](deploy.down.md) | Stops pipelines. |
| [cli-launch](cli-launch.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/deploy.py::launch` (lines 138-161)
