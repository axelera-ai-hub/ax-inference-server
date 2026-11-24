# server.vllm_up

## Summary

Launches a vLLM server for a compiled artifact.

## Detailed Description

### Behavior

The function posts to `/vllm/launch` with a 240 second timeout. The artifact path is `${SDK_ROOT}/build/<artifact>/axscript`. The device is sent by name.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`artifact` must name a build below `${SDK_ROOT}/build`. The device must be present because the function sends its name. The request timeout is 240 seconds.

## Signature

```python
def vllm_up(name: str, artifact: str, port: int, device: int, thinking: bool, temperature: float) -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| name | str | none | Yes | Instance name. |
| artifact | str | none | Yes | Artifact name below `${SDK_ROOT}/build`. |
| port | int | none | Yes | Port to serve on. |
| device | int | none | Yes | Device index. The function sends its name. |
| thinking | bool | none | Yes | Enable chat-template thinking mode. |
| temperature | float | none | Yes | Sampling temperature. |

## Returns

`dict`. The reply with `pid`, `port` and `context_length`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The device is not present. | Use a present device. |
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
res = server.vllm_up("qwen3-0.6b", "qwen3-0.6b", 8000, 0, False, 0.0)
```

## Edge Cases

- Startup takes 1-2 minutes.

## Related APIs

| API | Relationship |
|---|---|
| [cli-vllm-up](cli-vllm-up.md) | Command wrapper. |
| [server.device_name](server.device_name.md) | Resolves the device name. |

## Source Reference

- `client/examples/helper/server.py::vllm_up` (lines 357-373)
