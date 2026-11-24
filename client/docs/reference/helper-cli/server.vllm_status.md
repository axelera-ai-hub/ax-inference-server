# server.vllm_status

## Summary

Returns the vLLM instances the server knows about.

## Detailed Description

### Behavior

The function reads `/vllm/status`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def vllm_status() -> list[dict]
```

## Parameters

None.

## Returns

`list[dict]`. One entry per instance with `name`, `port`, `running`, `pid` and `context_length`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.vllm_status())
```

## Edge Cases

None beyond the exceptions above.


## Related APIs

| API | Relationship |
|---|---|
| [cli-vllm-status](cli-vllm-status.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::vllm_status` (lines 376-378)
