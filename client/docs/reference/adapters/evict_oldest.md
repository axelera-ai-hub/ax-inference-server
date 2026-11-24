# evict_oldest

## Summary

Records a saved file and deletes the oldest files beyond a retention limit.

## Detailed Description

### Behavior

The function appends `filename` to a per-directory queue held in module state. While the queue is longer than `keep_last_n`, it removes the oldest names and deletes those files from `directory`. Files that are already gone are ignored.

### Concurrency

A module-level lock guards the queue. File deletion runs outside the lock.

### Constraints

The queue grows only through this function. Call it once per saved file.

## Signature

```python
def evict_oldest(directory: str, filename: str, keep_last_n: int) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | yes | Directory the file was saved in. |
| filename | str | none | yes | Name of the newly saved file. |
| keep_last_n | int | none | yes | Number of most recent files to keep in this directory. |

## Returns

`None`.

## Exceptions

| Exception | Trigger |
|---|---|
| `IndexError` | `keep_last_n` is negative. `popleft` fails inside the lock. |
| `OSError` | `os.remove` fails with an error other than `FileNotFoundError`. |

When `IndexError` occurs, names already popped are lost from the queue. The function does not delete those files.

## Usage Examples

### Basic

```python
from adapters.common.rendering import evict_oldest

evict_oldest('/tmp/frames', 'f000002.jpg', keep_last_n=50)
```

## Edge Cases

- The module state is global and shared by all callers in the process.
- A `keep_last_n` of 0 removes every tracked file, including the new one.
- A negative `keep_last_n` raises `IndexError`.
- Files not recorded through this function are never deleted.

## Related APIs

| API | Relationship |
|---|---|
| [save_frame](save_frame.md) | Writes the file that this function records. |
| [reset_ring_buffer](reset_ring_buffer.md) | Forgets the tracked names. |

## Source Reference

- `client/adapters/common/rendering.py::evict_oldest` (lines 332-354)
