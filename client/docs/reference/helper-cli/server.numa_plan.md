# server.numa_plan

## Summary

Gets the server CPU plan for a set of devices.

## Detailed Description

### Behavior

The function reads `/devices/numa_plan` with the parameters `indices` and `cores_per_device`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`devices` must be a list of device indexes.

## Signature

```python
def numa_plan(devices: list[int], cores_per_device: int = 4) -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| devices | list[int] | none | Yes | Device indexes. |
| cores_per_device | int | 4 | No | CPU cores to reserve per device. |

## Returns

`dict`. The reply with a `plan` entry per device and `numa_available`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
plan = server.numa_plan([0, 1], 4)
```

## Edge Cases

- The function sends `devices` as a comma-separated `indices` parameter.


## Related APIs

| API | Relationship |
|---|---|
| [server.pin_groups](server.pin_groups.md) | Turns the plan into pinning values. |

## Source Reference

- `client/examples/helper/server.py::numa_plan` (lines 256-267)
