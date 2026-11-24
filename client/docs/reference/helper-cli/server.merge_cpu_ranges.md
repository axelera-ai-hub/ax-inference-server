# server.merge_cpu_ranges

## Summary

Collapses CPU ids into a taskset-style range string.

## Detailed Description

### Behavior

The function sorts the ids, removes duplicates and merges adjacent ids into `lo-hi` ranges.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def merge_cpu_ranges(cpus: list[int]) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| cpus | list[int] | none | Yes | CPU ids in any order. Duplicates are allowed. |

## Returns

`str`. Comma-separated ranges. `[0, 1, 2, 5]` gives `0-2,5`.

## Exceptions

None.

## Usage Examples

### Basic

```python
from helper import server
print(server.merge_cpu_ranges([0, 1, 2, 5]))
# 0-2,5
```

## Edge Cases

- An empty list gives an empty string.

## Related APIs

| API | Relationship |
|---|---|
| [server.pin_groups](server.pin_groups.md) | Caller. |

## Source Reference

- `client/examples/helper/server.py::merge_cpu_ranges` (lines 270-288)
