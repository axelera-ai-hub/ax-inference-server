# server.fetch_media

## Summary

Downloads the sample videos on the server and waits until the download ends.

## Detailed Description

### Behavior

The function posts to `/benchmark-media/fetch`. An HTTP 409 means a fetch already runs, so the function joins it. It then polls `/benchmark-media/status` until the fetch is no longer running and has a result.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The function checks `timeout_s` only while the fetch is still running. A finished fetch returns without a deadline check.

## Signature

```python
def fetch_media(poll_s: float = 5.0, timeout_s: float = 3600.0) -> list[dict]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| poll_s | float | 5.0 | No | Seconds between polls. |
| timeout_s | float | 3600.0 | No | Give up after this many seconds. |

## Returns

`list[dict]`. One result per file with `file`, `status` and `detail`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ServerError` | The fetch does not finish in time, or a request fails. | Retry. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```python
from helper import server
for r in server.fetch_media():
    print(r["file"], r["status"])
```

## Edge Cases

- The function does not raise for a file with status `error`. The CLI does.

## Related APIs

| API | Relationship |
|---|---|
| [cli-media](cli-media.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::fetch_media` (lines 313-342)
