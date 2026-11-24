# AsyncAxVisionClient

## Overview
`AsyncAxVisionClient` is the asyncio twin of [AxVisionClient](AxVisionClient.md). Constructor arguments, defaults and the engine are identical. This page lists only the differences. It subclasses [AsyncAxInferClient](AsyncAxInferClient.md).

## Attributes
Same as `AxVisionClient`: the `stats` property.

## Methods
| Method | Summary | Page |
|---|---|---|
| `infer(image_bytes, request_id, timeout)` | Coroutine version of `infer`. | [AsyncAxVisionClient.infer](AsyncAxVisionClient.infer.md) |
| `__aenter__()` / `__aexit__(*_)` | Async context manager. `__aexit__` calls the blocking `close()`. | [AsyncAxInferClient](AsyncAxInferClient.md) |
| `close()` | Not a coroutine. It blocks until workers stop. | [AsyncAxInferClient](AsyncAxInferClient.md) |
| `open_stream(on_result, ...)` | Same as the blocking client. | [AxInferClient.open_stream](AxInferClient.open_stream.md) |

## Initialization
Same as [AxVisionClient](AxVisionClient.md#initialization). The constructor raises `ValueError("num_workers must be positive")` when `num_workers <= 0`.

## Lifecycle
Use `async with AsyncAxVisionClient(...) as client`.

## Related Classes
| Class | Relationship |
|---|---|
| [AxVisionClient](AxVisionClient.md) | Blocking twin. |

## Source Reference
`client/inference/vision.py::AsyncAxVisionClient` (lines 83-118)
