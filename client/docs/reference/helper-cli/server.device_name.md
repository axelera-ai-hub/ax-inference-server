# server.device_name

## Summary

Looks up the name of a device.

## Detailed Description

### Behavior

The function reads `/devices` and returns the `name` of the matching index.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`index` must be a device index the server reports.

## Signature

```python
def device_name(index: int) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| index | int | none | Yes | Device index. |

## Returns

`str`. The device name.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The device is not present. | Use an index from `device_indexes`. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.device_name(0))
```

## Edge Cases

- The function returns the name of the first entry with a matching index.


## Related APIs

| API | Relationship |
|---|---|
| [server.vllm_up](server.vllm_up.md) | Sends the name to the server. |

## Source Reference

- `client/examples/helper/server.py::device_name` (lines 345-354)
