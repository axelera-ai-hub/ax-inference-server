# server.axdevice_status

## Summary

Returns the axdevice status of a device, including its power limit.

## Detailed Description

### Behavior

The function reads `/devices/<device>/axdevice` with a 60 second timeout.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The request timeout is 60 seconds.

## Signature

```python
def axdevice_status(device: int) -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| device | int | none | Yes | Device index. |

## Returns

`dict`. The status. The CLI reads the keys `device` and `power_limit_w`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.axdevice_status(0)["power_limit_w"])
```

## Edge Cases

- The request waits up to 60 seconds.


## Related APIs

| API | Relationship |
|---|---|
| [cli-power](cli-power.md) | Uses the status for `get`. |

## Source Reference

- `client/examples/helper/server.py::axdevice_status` (lines 226-228)
