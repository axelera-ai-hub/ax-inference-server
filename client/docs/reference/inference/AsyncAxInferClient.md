# AsyncAxInferClient

## Overview
`AsyncAxInferClient` is the asyncio twin of [AxInferClient](AxInferClient.md). Workers, shared memory, constructor arguments, `stats` and streaming are the same. This page lists only the differences. `AsyncAxVisionClient` subclasses it.

## Attributes
Same as `AxInferClient`: the `stats` property.

## Methods
| Method | Summary | Page |
|---|---|---|
| `__aenter__()` | Coroutine that returns the client itself. | this page |
| `__aexit__(*_)` | Coroutine that calls `close()`. | this page |
| `close()` | Regular method, not a coroutine. It blocks until the workers stop. | this page |
| `open_stream(on_result, ...)` | Same arguments and behavior as the blocking client. | [AxInferClient.open_stream](AxInferClient.open_stream.md) |

## Initialization
Same signature and defaults as [AxInferClient](AxInferClient.md#initialization). The constructor raises `ValueError("num_workers must be positive")` when `num_workers <= 0`.

## Lifecycle
Use `async with`. The client submits calls through `loop.run_in_executor`, so a full queue does not block the event loop. A cancelled call is unregistered and `asyncio.CancelledError` propagates. `__aexit__` runs the blocking `close()` on the event loop thread.

## Related Classes
| Class | Relationship |
|---|---|
| [AxInferClient](AxInferClient.md) | Blocking twin. |
| [AsyncAxVisionClient](AsyncAxVisionClient.md) | Subclass that adds `infer`. |

## Source Reference
`client/inference/_client.py::AsyncAxInferClient` (lines 147-243)
