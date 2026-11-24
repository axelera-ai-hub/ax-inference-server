# save_frame

## Summary

Writes a frame to disk atomically.

## Detailed Description

### Behavior

The function creates `directory` and a `.tmp` subdirectory if they are missing. It writes the image to `.tmp/<filename>` with `cv2.imwrite`. It then renames the file into `directory`. Readers never see a partial file.

### Concurrency

The function holds no lock. Use unique filenames when saving from several threads. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def save_frame(directory: str, filename: str, raw: np.ndarray) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | yes | Destination directory. The function creates it if missing. |
| filename | str | none | yes | File name. The extension selects the image format. |
| raw | np.ndarray | none | yes | BGR frame. |

## Returns

`str`. The path of the saved file.

## Exceptions

| Exception | Trigger |
|---|---|
| RuntimeError | `cv2.imwrite` returns `False`. |

## Usage Examples

### Basic

```python
from adapters.common.rendering import save_frame, evict_oldest

path = save_frame('/tmp/frames', 'f000001.jpg', frame.raw)
evict_oldest('/tmp/frames', 'f000001.jpg', keep_last_n=100)
```

## Edge Cases

- Two concurrent saves with the same filename in one directory share one temporary path.
- The `.tmp` directory remains after the call.

## Related APIs

| API | Relationship |
|---|---|
| [evict_oldest](evict_oldest.md) | Prunes old files after a save. |
| [reset_ring_buffer](reset_ring_buffer.md) | Clears the tracked names. |

## Source Reference

- `client/adapters/common/rendering.py::save_frame` (lines 303-329)
