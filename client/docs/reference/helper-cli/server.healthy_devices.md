# server.healthy_devices

## Summary

Health-checks devices and returns the usable ones.

## Detailed Description

### Behavior

The function lists the present devices. With `spec` equal to `auto`, it checks all of them and returns the first `num_devices` healthy indexes. With a list, it checks exactly those devices and requires all to be healthy. It logs one line per checked device.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`spec` must be `auto` or comma-separated integers. `num_devices` applies only to `auto`.

## Signature

```python
def healthy_devices(spec: str = 'auto', num_devices: int = 1) -> list[int]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| spec | str | `auto` | No | `auto`, or comma-separated indexes. |
| num_devices | int | 1 | No | With `auto`: how many healthy indexes to return. |

## Returns

`list[int]`. With `auto`, the first `num_devices` healthy indexes. Otherwise the requested indexes.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | A requested device is not present. | Use an index from `device_indexes`. |
| `ValueError` | `spec` is not `auto` and an item is not an integer, for example `0,x`. | Pass comma-separated integers. |
| `ServerError` | No devices exist, too few are healthy, or a requested device is unhealthy. | Pick healthy devices or use `auto`. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```python
from helper import server
print(server.healthy_devices("auto", 2))
```

## Edge Cases

- With `auto`, an unhealthy device is skipped.
- A malformed `spec` such as `0,x` raises `ValueError` after the device list request and before the health check.
- With an explicit list, `num_devices` has no effect.

## Related APIs

| API | Relationship |
|---|---|
| [server.device_indexes](server.device_indexes.md) | Lists present devices. |
| [server.device_health](server.device_health.md) | Checks health. |
| [cli-devices](cli-devices.md) | Command wrapper. |
| [config.isovision](config.isovision.md) | Caller. |

## Source Reference

- `client/examples/helper/server.py::healthy_devices` (lines 118-152)
