# server.check_health

## Summary

Queries the unauthenticated health endpoint.

## Detailed Description

### Behavior

The function sends `GET /api/v1/health` with a 10 second timeout and returns the JSON reply. It does not send the API key.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`HOST_SERVER_URL` must be set. The request timeout is 10 seconds.

## Signature

```python
def check_health() -> dict
```

## Parameters

None.

## Returns

`dict`. The parsed JSON reply.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` is unset. | Export `HOST_SERVER_URL`. |
| `ServerError` | The request fails or returns an error status. | Check the server. |

## Usage Examples

### Basic

```python
from helper import server
print(server.check_health())
```

## Edge Cases

- The function does not need `HOST_SERVER_API_KEY`.

## Related APIs

| API | Relationship |
|---|---|
| [cli-health](cli-health.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::check_health` (lines 79-97)
