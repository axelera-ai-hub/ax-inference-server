# Frame

## Overview

`Frame` is a dataclass that carries one captured frame from an adapter to the inference client. It holds both the JPEG bytes and the decoded BGR image.

## Attributes

| Attribute | Type | Description |
|---|---|---|
| encoded | bytes | JPEG-encoded image. Empty when the reader ran with `need_encoded=False`. |
| raw | np.ndarray | Decoded BGR image. |
| captured_at | float | `time.monotonic()` timestamp taken when the `Frame` is constructed. |
| sequence | int | Per-adapter counter assigned by `SourceAdapter.read_frame`. Defaults to 0. |

## Methods

This class has no methods.

## Initialization

```python
Frame(encoded: bytes, raw: np.ndarray, captured_at: float = <time.monotonic()>, sequence: int = 0)
```

## Lifecycle

The adapter subclass constructs the `Frame` in its read step. `SourceAdapter.read_frame` then overwrites `sequence`.

## Related Classes

| Class | Relationship |
|---|---|
| [SourceAdapter](SourceAdapter.md) | Produces frames. |

## Source Reference

- `client/adapters/base.py::Frame` (lines 21-35)
