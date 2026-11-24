# SourceAdapterError

## Overview

`SourceAdapterError` is a `RuntimeError` subclass. Adapters raise it when they cannot open, read from or encode their source.

## Attributes

This class adds no attributes.

## Methods

This class has no methods.

## Initialization

```python
SourceAdapterError(message: str)
```

The constructor is the one from `RuntimeError`.

## Lifecycle

Adapters raise the error from `open()`, `read_frame()` and the JPEG encoding step. The caller catches it to handle a failed source.

## Related Classes

| Class | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Raises it when `read_frame()` is called before `open()`. |
| [WebcamAdapterCV](WebcamAdapterCV.md) | Raises it when the device disconnects. |

## Source Reference

- `client/adapters/base.py::SourceAdapterError` (lines 15-18)
