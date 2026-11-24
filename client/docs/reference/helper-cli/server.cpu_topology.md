# server.cpu_topology

## Summary

Returns the host CPU and NUMA topology.

## Detailed Description

### Behavior

The function reads `/devices/cpu_topology`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def cpu_topology() -> dict
```

## Parameters

None.

## Returns

`dict`. The topology. The CLI reads `numa_available`, `total_cpus` and `nodes`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.cpu_topology())
```

## Edge Cases

None beyond the exceptions above.


## Related APIs

| API | Relationship |
|---|---|
| [cli-pin](cli-pin.md) | Prints the topology summary. |

## Source Reference

- `client/examples/helper/server.py::cpu_topology` (lines 251-253)
