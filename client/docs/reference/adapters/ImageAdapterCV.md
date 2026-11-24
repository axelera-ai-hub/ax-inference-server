# ImageAdapterCV

## Overview

`ImageAdapterCV` serves one still image repeatedly. `open()` decodes the file and JPEG-encodes it once. Every read returns the same cached buffers. The adapter never reports end of stream. `source_kind` is `'image'`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| source_kind | str | `'image'`. |
| display_name | str (property) | File name of the image without its directory. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `open()`, `close()`, `read_frame()` | Inherited from the base class. | [SourceAdapter](SourceAdapter.md) |

## Initialization

```python
ImageAdapterCV(path: str, *, target_fps: float = 30.0, jpeg_quality: int = 90)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| path | str | required | Path of the image file. |
| target_fps | float | `30.0` | Desired read rate. |
| jpeg_quality | int | `90` | JPEG quality for the cached encoding. |

## Lifecycle

`open()` reads the image as BGR with `cv2.imread` and raises `SourceAdapterError` if the read fails. `read_frame()` returns a `Frame` that wraps the cached image and ignores `need_encoded`. Frames always carry the cached JPEG bytes. `close()` drops the cached buffers.

## Related Classes

| Class | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Base class. |
| [Frame](Frame.md) | Value type that it yields. |

## Source Reference

- `client/adapters/image_cv.py::ImageAdapterCV` (lines 13-64)
