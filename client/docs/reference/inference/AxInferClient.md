# AxInferClient

## Overview
`AxInferClient` is the blocking base client for cross-process calls to gRPC endpoints. It packs each call into shared memory. Worker processes run an engine of the class you pass and return the responses. `AxVisionClient` subclasses it. The package exports it as `from inference import AxInferClient`. The client has no `infer` method of its own. Subclasses add one.

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `stats` | counter object | Property with the fields `total_count` (responses received) and `failed_count` (responses with a non-zero status). |

## Methods
| Method | Summary | Page |
|---|---|---|
| `__init__(engine_cls, endpoints, concurrency, num_workers, shm_ring_size, shm_slot_size_bytes)` | Creates the engine without starting workers. | this page |
| `__enter__()` | Returns the client itself. | this page |
| `__exit__(*_)` | Calls `close()`. | this page |
| `close()` | Stops the workers and releases shared memory. Safe to call more than once. | this page |
| `open_stream(on_result, ...)` | Opens a callback stream for pipelined calls. | [AxInferClient.open_stream](AxInferClient.open_stream.md) |

## Initialization
```python
AxInferClient(
    engine_cls,
    endpoints: list[str],
    concurrency: int = 1000,
    num_workers: int = 1,
    shm_ring_size: int = 64,
    shm_slot_size_bytes: int = 1048576,
)
```

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `engine_cls` | class | none | yes | Engine class each worker creates as `engine_cls(endpoints, concurrency=...)`. |
| `endpoints` | `list[str]` | none | yes | Server addresses as `host:port`. |
| `concurrency` | `int` | `1000` | no | Total in-flight request budget, split across workers. |
| `num_workers` | `int` | `1` | no | Number of worker processes. |
| `shm_ring_size` | `int` | `64` | no | Number of shared-memory slots. |
| `shm_slot_size_bytes` | `int` | `1048576` | no | Slot capacity in bytes. A call with a larger packed payload fails. |

The constructor raises `ValueError("num_workers must be positive")` when `num_workers <= 0`.

## Lifecycle
1. The constructor creates the engine. No process starts.
2. The first call or `open_stream()` spawns the worker processes and a dispatcher thread.
3. The retry and timeout settings of that first call apply to all later calls.
4. `close()` or leaving the `with` block stops the workers.

The first `open_stream()` call per client replaces any earlier stream as the receiver of unmatched results. Use one stream at a time.

## Related Classes
| Class | Relationship |
|---|---|
| [AsyncAxInferClient](AsyncAxInferClient.md) | Asyncio twin. |
| [AxVisionClient](AxVisionClient.md) | Subclass that adds `infer` for the vision service. |

## Source Reference
`client/inference/_client.py::AxInferClient` (lines 21-144)
