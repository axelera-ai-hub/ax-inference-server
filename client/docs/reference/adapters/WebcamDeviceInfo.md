# WebcamDeviceInfo

## Overview

`WebcamDeviceInfo` is a dataclass that describes one V4L2 capture device found under `/dev`. `WebcamAdapterCV.list_devices` returns a list of these.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| path | str | Device node, for example `'/dev/video0'`. |
| index | int | Numeric suffix of the device node. |
| display_name | str | Label shown to the user, for example `'USB 0'`. |

## Methods

This class has no methods.

## Initialization

```python
WebcamDeviceInfo(path: str, index: int, display_name: str)
```

## Lifecycle

`list_devices` creates the instances. They are plain values with no lifecycle.

## Related Classes

| Class | Relationship |
|---|---|
| [WebcamAdapterCV](WebcamAdapterCV.md) | Provides `list_devices`. |

## Source Reference

- `client/adapters/webcam_cv.py::WebcamDeviceInfo` (lines 15-27)
