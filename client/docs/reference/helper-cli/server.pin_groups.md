# server.pin_groups

## Summary

Plans CPU pinning for groups of devices.

## Detailed Description

### Behavior

The function requests one plan for all devices and merges the CPUs of each group into a range string. `membind` is the NUMA node of the first device of the group.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

Each group must be non-empty and hold indexes the server plans.

## Signature

```python
def pin_groups(groups: list[list[int]], cores_per_device: int = 4) -> list[dict]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| groups | list[list[int]] | none | Yes | Device indexes per pipeline. |
| cores_per_device | int | 4 | No | CPU cores reserved per device. |

## Returns

`list[dict]`. One entry per group with `taskset_cpus` and `membind`. `membind` is `None` when NUMA is unavailable.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import server
print(server.pin_groups([[0], [1]]))
```

## Edge Cases

- A group must be non-empty.

## Related APIs

| API | Relationship |
|---|---|
| [server.numa_plan](server.numa_plan.md) | Provides the plan. |
| [server.merge_cpu_ranges](server.merge_cpu_ranges.md) | Formats the CPUs. |
| [cli-pin](cli-pin.md) | Command wrapper. |
| [config.isovision](config.isovision.md) | Caller with `--pin`. |

## Source Reference

- `client/examples/helper/server.py::pin_groups` (lines 291-310)
