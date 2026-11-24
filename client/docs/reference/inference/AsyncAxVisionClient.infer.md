# AsyncAxVisionClient.infer

## Summary
`infer` awaits the `FrameResult` for one encoded image. It is the async twin of [AxVisionClient.infer](AxVisionClient.infer.md).

## Detailed Description
### Behavior
Parameters, return value and the `TimeoutError`, `RuntimeError` and `ValueError` exceptions are the same as in the blocking method. Differences follow.

### Concurrency
The method is a coroutine. It submits through `loop.run_in_executor` and waits with `asyncio.wait_for`. Cancelling the task unregisters the pending call and re-raises `asyncio.CancelledError`.

## Signature
```python
async AsyncAxVisionClient.infer(image_bytes: bytes, request_id: Optional[str] = None, timeout: float = 60.0) -> FrameResult
```

## Parameters
Same as [AxVisionClient.infer](AxVisionClient.infer.md#parameters).

## Returns
`FrameResult`.

## Exceptions
Same as the blocking method, plus `asyncio.CancelledError` on cancellation.

## Usage Examples
### Basic
```python
import asyncio
from inference import AsyncAxVisionClient

async def main():
    async with AsyncAxVisionClient(["localhost:50060"]) as client:
        result = await client.infer(image_bytes)

asyncio.run(main())
```

## Edge Cases
- `asyncio.gather` over many `infer` calls pipelines requests up to `concurrency`.

## Related APIs
| API | Relationship |
|---|---|
| [AxVisionClient.infer](AxVisionClient.infer.md) | Blocking twin. |

## Source Reference
`client/inference/vision.py::AsyncAxVisionClient.infer` (lines 101-118)
