# AxVisionClient.infer

## Summary
`infer` sends one encoded image and blocks until the `FrameResult` arrives.

## Detailed Description
### Behavior
The method submits the image as an `InferRequest` with `image_data` set. It waits up to `timeout` seconds. If `infer` starts the workers, the call has no client-side retry and no per-request timeout. If `open_stream` started the workers first, the retry and timeout settings of that stream apply to `infer`. Use `open_stream` with `retries_per_frame` to set retries.

### Concurrency
The engine limits in-flight calls with `concurrency`. Concurrency behavior depends on the underlying runtime.

### Constraints
The packed image must fit in `shm_slot_size_bytes`.

## Signature
```python
AxVisionClient.infer(image_bytes: bytes, request_id: Optional[str] = None, timeout: float = 60.0) -> FrameResult
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `image_bytes` | `bytes` | none | yes | Encoded image data, for example JPEG. |
| `request_id` | `Optional[str]` | `None` | no | Id sent with the request. The engine generates one per attempt if `None`. |
| `timeout` | `float` | `60.0` | no | Seconds to wait for the response. |

## Returns
`FrameResult`: the server response message (`axinfer.v1.inference_pb2`).

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `TimeoutError` | No response within `timeout`. | Raise `timeout` or check the server. |
| `RuntimeError` | The response has a non-zero status (message `infer() dropped: ...`), or the engine closed during submit. | Retry the call or open a new client. |
| `ValueError` | The packed payload exceeds the slot size. | Raise `shm_slot_size_bytes`. |

## Usage Examples
### Basic
```python
from inference import AxVisionClient

with AxVisionClient(["localhost:50060"]) as client:
    result = client.infer(image_bytes)
    print(len(result.detections))
```

## Edge Cases
- A client-side failure returns a `FrameResult` with status `DROPPED`, which `infer` converts to `RuntimeError`.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxVisionClient.infer](AsyncAxVisionClient.infer.md) | Async twin. |
| [AxInferClient.open_stream](AxInferClient.open_stream.md) | Pipelined alternative with retries. |

## Source Reference
`client/inference/vision.py::AxVisionClient.infer` (lines 65-80)
