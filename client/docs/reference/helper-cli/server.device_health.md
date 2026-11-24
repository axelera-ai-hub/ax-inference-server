# server.device_health

## Summary

Health-checks devices on the server.

## Detailed Description

### Behavior

The function posts the indexes to `/devices/health` and returns the report list.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`indexes` must hold device indexes. The default `timeout` is 900.0 seconds.

## Signature

```python
def device_health(indexes: list[int], timeout: float = 900.0) -> list[dict]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| indexes | list[int] | none | Yes | Device indexes. |
| timeout | float | 900.0 | No | Request timeout in seconds. |

## Returns

`list[dict]`. One report per device with at least `index`, `name` and `healthy`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.device_health([0]))
```

## Edge Cases

- The default `timeout` is 900.0 seconds.

## Related APIs

| API | Relationship |
|---|---|
| [server.healthy_devices](server.healthy_devices.md) | Filters the report. |

## Source Reference

- `client/examples/helper/server.py::device_health` (lines 105-115)
