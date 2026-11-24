# AxInferClient.open_stream

## Summary
`open_stream` opens a streaming session that delivers each result to a callback.

## Detailed Description
### Behavior
The call starts the workers if they are not running. It returns a stream object. `stream.push(*args, **kwargs)` submits one call. The arguments go to the engine's request builder. For the vision client, `push(image_bytes, request_id=None)` is valid. `stream.close(timeout=60.0)` waits for in-flight calls and detaches the stream. If calls remain after the timeout, `close` prints a warning to stderr and returns. The stream also works as a context manager and calls `close()` on exit.

### Concurrency
The dispatcher thread calls `on_result(sequence, response)`. The sequence counts pushes from 0. With `ordered=True` the stream holds each response until all earlier sequences are delivered. `push` blocks while no shared-memory slot or work-queue capacity is free.

### Constraints
The retry and timeout settings take effect only if this call starts the workers. Use one stream per client at a time.

## Signature
```python
AxInferClient.open_stream(
    on_result: Callable[[int, object], None],
    ordered: bool = False,
    retries_per_frame: int = 0,
    retry_base_delay_sec: float = 0.05,
    retry_max_delay_sec: float = 2.0,
    request_timeout_sec: Optional[float] = 20.0,
)
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `on_result` | `Callable[[int, object], None]` | none | yes | Called as `on_result(sequence, response)` from the dispatcher thread. |
| `ordered` | `bool` | `False` | no | Deliver in push order instead of completion order. |
| `retries_per_frame` | `int` | `0` | no | Retries for dropped or transiently failed calls. |
| `retry_base_delay_sec` | `float` | `0.05` | no | First retry delay. It doubles per attempt. |
| `retry_max_delay_sec` | `float` | `2.0` | no | Upper bound on the retry delay. |
| `request_timeout_sec` | `Optional[float]` | `20.0` | no | Per-request gRPC deadline. `None` or a value of 0 or less means no deadline. |

## Returns
The stream object with `push(*args, **kwargs)`, `close(timeout=60.0)`, `__enter__` and `__exit__`.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | `push` runs while the engine closes. | Create a new client. |
| `ValueError` | A pushed payload exceeds `shm_slot_size_bytes`. | Raise `shm_slot_size_bytes`. |
| `TypeError` | A pushed argument has an unsupported type. | Pass bytes, str, numbers, bool, None, or tuples, lists and dicts of those. |

## Usage Examples
### Basic
```python
from inference import AxVisionClient

results = {}

def on_result(seq, response):
    results[seq] = response

with AxVisionClient(["localhost:50060"]) as client:
    with client.open_stream(on_result, ordered=True) as stream:
        for image_bytes in images:
            stream.push(image_bytes)
```

## Edge Cases
- `AsyncAxInferClient.open_stream` is identical and is not a coroutine.
- A response with an unknown frame id is ignored.

## Related APIs
| API | Relationship |
|---|---|
| [AxInferClient](AxInferClient.md) | Owner class. |
| [AsyncAxInferClient](AsyncAxInferClient.md) | Async twin with the same method. |
| [AxVisionClient.infer](AxVisionClient.infer.md) | Single blocking call. |

## Source Reference
`client/inference/_client.py::AxInferClient.open_stream` (lines 113-144)
