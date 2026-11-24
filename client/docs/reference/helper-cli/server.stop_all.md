# server.stop_all

## Summary

Stops every pipeline and vLLM server on the host.

## Detailed Description

### Behavior

The function posts to `/pipelines/cleanup-all` with a 120 second timeout.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The request timeout is 120 seconds.

## Signature

```python
def stop_all() -> dict
```

## Parameters

None.

## Returns

`dict`. The reply with `killed_pids` and `killed_vllm_names`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.stop_all())
```

## Edge Cases

- The request waits up to 120 seconds.


## Related APIs

| API | Relationship |
|---|---|
| [cli-stop-all](cli-stop-all.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::stop_all` (lines 180-186)
