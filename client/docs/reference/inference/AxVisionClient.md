# AxVisionClient

## Overview
`AxVisionClient` is the blocking client for the AxInference vision gRPC service. It sends encoded images to one or more endpoints and returns `FrameResult` messages. It subclasses [AxInferClient](AxInferClient.md) and fixes the engine class. See the [gRPC interface](../../../../server/docs/interfaces/grpc.md) and the [client concept page](../../client/client.md).

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `stats` | counter object | Inherited. Has the fields `total_count` and `failed_count`. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `infer(image_bytes, request_id, timeout)` | Runs one image and returns a `FrameResult`. | [AxVisionClient.infer](AxVisionClient.infer.md) |
| `open_stream(on_result, ...)` | Inherited. Opens a callback stream. | [AxInferClient.open_stream](AxInferClient.open_stream.md) |
| `close()` | Inherited. Stops the workers. | [AxInferClient](AxInferClient.md) |
| `__enter__()` / `__exit__(*_)` | Inherited. Context manager that closes the client on exit. | [AxInferClient](AxInferClient.md) |

## Initialization
```python
AxVisionClient(
    endpoints: list[str],
    *,
    concurrency: int = 1000,
    num_workers: int = 1,
    shm_ring_size: int = 64,
    shm_slot_size_bytes: int = 1048576,
)
```
All arguments after `endpoints` are keyword-only. Each slot must hold one encoded image. Other meanings are as in [AxInferClient](AxInferClient.md#initialization). The constructor raises `ValueError("num_workers must be positive")` when `num_workers <= 0`.

## Lifecycle
Workers start on the first `infer` or `open_stream` call. `close()` stops them.

## Related Classes
| Class | Relationship |
|---|---|
| [AsyncAxVisionClient](AsyncAxVisionClient.md) | Asyncio twin. |
| [AxInferClient](AxInferClient.md) | Base class. |

## Source Reference
`client/inference/vision.py::AxVisionClient` (lines 36-80)
