# WebcamAdapterCV.list_devices

## Summary

Lists the `/dev/video*` capture devices, sorted by path.

## Detailed Description

### Behavior

The static method globs `/dev/video*` and sorts the paths. It skips paths that do not end in a number. With `probe=True` it opens `cv2.VideoCapture(index)` by index for each device. A failed open skips the device. Each entry gets the label `USB <index>`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Linux V4L2 device nodes only.

## Signature

```python
@staticmethod
def list_devices(*, probe: bool = True) -> List[WebcamDeviceInfo]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| probe | bool | `True` | no | Open each device with OpenCV and skip those that cannot be opened. |

## Returns

`List[WebcamDeviceInfo]`. One entry per device whose path ends in a number.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters import WebcamAdapterCV

for dev in WebcamAdapterCV.list_devices():
    print(dev.path, dev.display_name)
```

## Edge Cases

- The method returns an empty list on hosts without `/dev/video*`.

## Related APIs

| API | Relationship |
|---|---|
| [WebcamDeviceInfo](WebcamDeviceInfo.md) | Entry type. |
| [WebcamAdapterCV](WebcamAdapterCV.md) | Owning class. |

## Source Reference

- `client/adapters/webcam_cv.py::WebcamAdapterCV.list_devices` (lines 96-119)
