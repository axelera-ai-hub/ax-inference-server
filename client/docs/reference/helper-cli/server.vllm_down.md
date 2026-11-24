# server.vllm_down

## Summary

Stops a vLLM instance.

## Detailed Description

### Behavior

The function posts the name to `/vllm/shutdown` with a 60 second timeout.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The request timeout is 60 seconds.

## Signature

```python
def vllm_down(name: str) -> bool
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| name | str | none | Yes | Instance name. |

## Returns

`bool`. `True` if the instance was running and has stopped.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
stopped = server.vllm_down("qwen3-0.6b")
```

## Edge Cases

- `False` means the server did not start that instance or it was not running.

## Related APIs

| API | Relationship |
|---|---|
| [cli-vllm-down](cli-vllm-down.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::vllm_down` (lines 381-387)
