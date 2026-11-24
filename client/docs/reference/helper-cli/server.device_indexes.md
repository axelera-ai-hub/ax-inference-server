# server.device_indexes

## Summary

Returns the sorted indexes of the devices the server reports.

## Detailed Description

### Behavior

The function reads `GET /devices` and sorts the `index` values.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def device_indexes() -> list[int]
```

## Parameters

None.

## Returns

`list[int]`. Sorted device indexes. Empty when the server reports none.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.device_indexes())
```

## Edge Cases

- The function returns an empty list when the server reports no devices.


## Related APIs

| API | Relationship |
|---|---|
| [server.healthy_devices](server.healthy_devices.md) | Uses the indexes. |
| [server.select_first_healthy](server.select_first_healthy.md) | Uses the indexes. |

## Source Reference

- `client/examples/helper/server.py::device_indexes` (lines 100-102)
