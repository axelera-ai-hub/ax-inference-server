# server.list_models

## Summary

Lists the models known to the server.

## Detailed Description

### Behavior

The function reads `/prebuilt-models`, `/models` and `/vllm/artifacts`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def list_models() -> dict
```

## Parameters

None.

## Returns

`dict`. Name lists under `prebuilt`, `vision_built`, `vlm_built` and `vllm_artifacts`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.list_models()["prebuilt"])
```

## Edge Cases

- `/models` is requested twice.

## Related APIs

| API | Relationship |
|---|---|
| [cli-models-list](cli-models-list.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/server.py::list_models` (lines 189-200)
