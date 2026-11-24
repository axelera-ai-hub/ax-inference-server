# SourceAdapter

## Overview

`SourceAdapter` is the abstract base class for objects that produce `Frame` values from a video, image or camera source. Subclasses implement the open, close and read-frame steps and `display_name`. The base class tracks the open state, numbers the frames and works as a context manager. See the [adapters concept page](../../client/adapters.md).

## Attributes

| Attribute | Type | Description |
|---|---|---|
| source_kind | str | Short label for the source type, such as `'video_file'`. Defaults to `'unknown'`. |
| is_open | bool (property) | `True` after `open()` succeeds and until `close()` is called. |
| target_fps | float (property) | Desired read rate in frames per second. The setter raises `ValueError` if the value is not positive. |
| display_name | str (abstract property) | Human-readable name of the source, shown in the UI. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `__init__(*, target_fps)` | Creates the adapter in the closed state. | This page |
| `open()` | Opens the source. Does nothing if already open. | This page |
| `close()` | Releases the source. Does nothing if not open. | This page |
| `__enter__()` | Opens the adapter and returns it. | This page |
| `__exit__(*_exc)` | Closes the adapter and does not suppress exceptions. | This page |
| `read_frame(*, need_encoded=True)` | Reads and numbers the next frame. | [SourceAdapter.read_frame](SourceAdapter.read_frame.md) |

## Initialization

```python
def __init__(self, *, target_fps: float) -> None
```

`target_fps` is keyword-only and must be positive. The constructor raises `ValueError` otherwise.

## Lifecycle

1. The constructor creates the adapter closed.
2. `open()` calls the subclass open step and marks the adapter open.
3. `read_frame()` returns frames until the source ends or fails.
4. `close()` calls the subclass close step and marks the adapter closed.

The `with` statement runs steps 2 and 4. The adapter is not thread-safe. Use one adapter from one thread at a time.

## Related Classes

| Class | Relationship |
|---|---|
| [Frame](Frame.md) | Value type that `read_frame` returns. |
| [SourceAdapterError](SourceAdapterError.md) | Error type that adapters raise. |
| [VideoFileAdapterCV](VideoFileAdapterCV.md) | Subclass for video files. |
| [ImageAdapterCV](ImageAdapterCV.md) | Subclass for still images. |
| [WebcamAdapterCV](WebcamAdapterCV.md) | Subclass for cameras. |

## Source Reference

- `client/adapters/base.py::SourceAdapter` (lines 38-149)
