# VideoFileAdapterCV

## Overview

`VideoFileAdapterCV` reads frames from a video file with `cv2.VideoCapture`. It can loop back to the first frame at the end of the file. Without a `target_fps`, it adopts the file's native frame rate after `open()`. `source_kind` is `'video_file'`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| source_kind | str | `'video_file'`. |
| display_name | str (property) | File name of the video without its directory. |
| target_fps | float (property) | Read rate. Starts at the requested value or 30.0, then becomes the native rate after `open()` if none was requested. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `open()`, `close()`, `read_frame()` | Inherited from the base class. | [SourceAdapter](SourceAdapter.md) |

## Initialization

```python
VideoFileAdapterCV(path: str, *, target_fps: Optional[float] = None, loop: bool = True, jpeg_quality: int = 90)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| path | str | required | Path of the video file. |
| target_fps | Optional[float] | `None` | Desired read rate. If `None`, the native FPS is used, with 30.0 as the fallback. |
| loop | bool | `True` | Restart from the first frame at end of file instead of returning `None`. |
| jpeg_quality | int | `90` | JPEG quality for encoded frames. |

The constructor does not open the file.

## Lifecycle

`open()` creates the `cv2.VideoCapture` and raises `SourceAdapterError` if the file cannot be opened. `read_frame()` returns `None` at end of file when `loop=False`. With `loop=True` it seeks to frame 0 and reads again. It raises `SourceAdapterError` if the file yields no frame after the rewind. With `need_encoded=False`, `Frame.encoded` is empty. `close()` releases the capture.

## Related Classes

| Class | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Base class. |
| [Frame](Frame.md) | Value type that it yields. |

## Source Reference

- `client/adapters/video_file_cv.py::VideoFileAdapterCV` (lines 14-92)
