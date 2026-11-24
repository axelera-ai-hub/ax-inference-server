# server.set_power_limit

## Summary

Sets or clears the power limit of a device.

## Detailed Description

### Behavior

The function converts `limit` to a float, or keeps `off`. It posts `power_limit_w` and `confirm` true to `/devices/<device>/axdevice` with a 120 second timeout.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`limit` must be a number of watts or `off`. The request timeout is 120 seconds.

## Signature

```python
def set_power_limit(device: int, limit: str) -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| device | int | none | Yes | Device index. |
| limit | str | none | Yes | Watts as a number, or `off`. |

## Returns

`dict`. The reply with `ok`, `device_before`, `device_after`, `power_limit_w_after` and `steps`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `limit` is neither a number nor `off`. | Pass watts or `off`. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
res = server.set_power_limit(0, "25")
```

## Edge Cases

- The function does not check the `ok` field. The CLI does.

## Related APIs

| API | Relationship |
|---|---|
| [cli-power](cli-power.md) | Command wrapper. |
| [server.axdevice_status](server.axdevice_status.md) | Reads the limit. |

## Source Reference

- `client/examples/helper/server.py::set_power_limit` (lines 231-248)
