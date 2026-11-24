# reset_ring_buffer

## Summary

Forgets the tracked file names for a directory without deleting files.

## Detailed Description

### Behavior

The function removes the directory's entry from the module state under the lock. Files on disk stay in place.

### Concurrency

A module-level lock guards the module state.

### Constraints

None beyond the parameter types.

## Signature

```python
def reset_ring_buffer(directory: str) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | yes | Directory whose tracked names are dropped. |

## Returns

`None`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import reset_ring_buffer

reset_ring_buffer('/tmp/frames')
```

## Edge Cases

- An unknown directory is ignored.
- Files recorded before the reset are no longer evicted.

## Related APIs

| API | Relationship |
|---|---|
| [evict_oldest](evict_oldest.md) | Adds names to the queue that this function clears. |

## Source Reference

- `client/adapters/common/rendering.py::reset_ring_buffer` (lines 357-360)
