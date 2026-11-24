# server.select_first_healthy

## Summary

Finds the first healthy device, trying a preferred index first.

## Detailed Description

### Behavior

The function orders the present devices with `preferred` first, then the others by index. It health-checks them one at a time and returns the first healthy index.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The function raises when no device is present or none is healthy.

## Signature

```python
def select_first_healthy(preferred: int = 0) -> int
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| preferred | int | 0 | No | Index tried first when present. |

## Returns

`int`. The device index.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `ServerError` | No device is healthy. | Check the devices. The message lists each failure. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```python
from helper import server
dev = server.select_first_healthy()
```

## Edge Cases

- The helper `vllm up --device` help text states that a device running vLLM is not healthy.
- The function returns after the first healthy device and checks no further devices.

## Related APIs

| API | Relationship |
|---|---|
| [server.device_health](server.device_health.md) | Checks each device. |
| [cli-devices](cli-devices.md) | Command wrapper with `--first`. |

## Source Reference

- `client/examples/helper/server.py::select_first_healthy` (lines 155-177)
