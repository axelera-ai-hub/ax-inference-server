# WebcamAdapterCV

## Overview

`WebcamAdapterCV` reads live frames from a camera with `cv2.VideoCapture`. A failed read counts as a disconnected device and raises. The stream never ends normally. `source_kind` is `'webcam'`.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| source_kind | str | `'webcam'`. |
| display_name | str (property) | `'USB N'` for an index or a `/dev/videoN` path. Otherwise the raw device string. |

## Methods

| Method | Summary | Page |
|---|---|---|
| `list_devices(*, probe=True)` | Static method that lists `/dev/video*` capture devices. | [WebcamAdapterCV.list_devices](WebcamAdapterCV.list_devices.md) |
| `open()`, `close()`, `read_frame()` | Inherited from the base class. | [SourceAdapter](SourceAdapter.md) |

## Initialization

```python
WebcamAdapterCV(device: Union[int, str], *, target_fps: float = 30.0, jpeg_quality: int = 90)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| device | Union[int, str] | required | Camera index or device path such as `'/dev/video0'`. |
| target_fps | float | `30.0` | Frame rate requested from the camera. |
| jpeg_quality | int | `90` | JPEG quality for encoded frames. |

## Lifecycle

`open()` creates the `cv2.VideoCapture`, raises `SourceAdapterError` if the device does not open, and sets `cv2.CAP_PROP_FPS` to `target_fps` once. `read_frame()` raises `SourceAdapterError` when a read fails. With `need_encoded=False`, `Frame.encoded` is empty. `close()` releases the capture.

## Related Classes

| Class | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Base class. |
| [WebcamDeviceInfo](WebcamDeviceInfo.md) | Result type of `list_devices`. |

## Source Reference

- `client/adapters/webcam_cv.py::WebcamAdapterCV` (lines 30-119)
