# server.require_env

## Summary

Reads the server URL and API key from the environment.

## Detailed Description

### Behavior

The function reads `HOST_SERVER_URL` and `HOST_SERVER_API_KEY`. It strips a trailing slash from the URL.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

`HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must both be non-empty.

## Signature

```python
def require_env() -> tuple[str, str]
```

## Parameters

None.

## Returns

`tuple[str, str]`. The URL and the API key.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```python
from helper import server
url, key = server.require_env()
```

## Edge Cases

- An empty value counts as unset.

## Related APIs

| API | Relationship |
|---|---|
| [server.api](server.api.md) | Calls `require_env` for every request. |
| [server.check_health](server.check_health.md) | Reads only the URL. |

## Source Reference

- `client/examples/helper/server.py::require_env` (lines 35-47)
