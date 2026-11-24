# deploy.down

## Summary

Stops each named pipeline and logs whether it was running.

## Detailed Description

### Behavior

For each id, the function posts to `/pipelines/shutdown` and logs `stopped` or `not running (not started by this server)`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Each request waits up to 60 seconds.

## Signature

```python
def down(ids: list[str]) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| ids | list[str] | none | Yes | Pipeline ids. |

## Returns

`None`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import deploy
deploy.down(["iso-detect"])
```

## Edge Cases

- A pipeline that is not running is not an error.
- A request failure stops the loop.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.pipeline_ids](deploy.pipeline_ids.md) | Resolves the ids. |
| [cli-down](cli-down.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/deploy.py::down` (lines 184-188)
