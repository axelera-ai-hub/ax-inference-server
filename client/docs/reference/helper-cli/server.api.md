# server.api

## Summary

Calls an `/api/v1` endpoint with the API key.

## Detailed Description

### Behavior

The function sends the request to `<HOST_SERVER_URL>/api/v1<path>` with the header `X-API-Key`. It returns the response only for status 200. For other statuses it raises with the `detail` field, cut to 400 characters.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`path` must start with `/`. The function builds `<HOST_SERVER_URL>/api/v1<path>`. The default `timeout` is 30.0 seconds.

## Signature

```python
def api(method: str, path: str, timeout: float = 30.0, **kwargs) -> httpx.Response
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| method | str | none | Yes | HTTP method. |
| path | str | none | Yes | Path below `/api/v1`, starting with `/`. |
| timeout | float | 30.0 | No | Request timeout in seconds. |
| **kwargs | any | none | No | Passed to `httpx.request`, for example `json` or `params`. |

## Returns

`httpx.Response`. The response, always with status 200.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | Transport error or any non-200 status. | Read the message and check the server. |

## Usage Examples

### Basic

```python
from helper import server
print(server.api("GET", "/devices").json())
```

## Edge Cases

- The message has the form `<METHOD> <path>: HTTP <status>: <detail>`.

## Related APIs

| API | Relationship |
|---|---|
| [server.require_env](server.require_env.md) | Provides URL and key. |
| [server.ServerError](server.ServerError.md) | Raised on failure. |

## Source Reference

- `client/examples/helper/server.py::api` (lines 50-76)
