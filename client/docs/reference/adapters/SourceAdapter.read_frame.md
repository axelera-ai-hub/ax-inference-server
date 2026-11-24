# SourceAdapter.read_frame

## Summary

Reads the next frame from an open adapter and numbers it.

## Detailed Description

### Behavior

The method raises if the adapter is closed. It calls the subclass read step. It returns `None` when that step returns `None`. Otherwise it sets `Frame.sequence` to the adapter's counter and increments the counter. The counter starts at 0 and is not reset by `close()`.

### Concurrency

The adapter is not thread-safe. Use one adapter from one thread at a time.

### Constraints

None beyond the parameter types.

## Signature

```python
def read_frame(self, *, need_encoded: bool = True) -> Optional[Frame]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| need_encoded | bool | `True` | no | Whether to JPEG-encode the frame. Subclasses can return empty `Frame.encoded` when `False`. |

## Returns

`Optional[Frame]`. The next frame, or `None` when the source is exhausted.

## Exceptions

| Exception | Trigger |
|---|---|
| SourceAdapterError | The adapter is not open, or the subclass fails to read. |

## Usage Examples

### Basic

```python
from adapters import VideoFileAdapterCV

with VideoFileAdapterCV('clip.mp4', loop=False) as src:
    while (frame := src.read_frame()) is not None:
        print(frame.sequence, len(frame.encoded))
```

## Edge Cases

- The method does not pace itself to `target_fps`.
- `ImageAdapterCV` ignores `need_encoded`.
- `VideoFileAdapterCV` returns `None` only when `loop=False`.
- `WebcamAdapterCV` never returns `None`.

## Related APIs

| API | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Owning class. |
| [Frame](Frame.md) | Return type. |

## Source Reference

- `client/adapters/base.py::SourceAdapter.read_frame` (lines 96-116)
