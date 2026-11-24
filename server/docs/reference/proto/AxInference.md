# AxInference

## Summary

`AxInference` is the gRPC service of the vision server. It has one unary RPC, `Infer`.

## Detailed Description

### Behavior

`Infer` takes one [InferRequest](InferRequest.md) and returns one [FrameResult](FrameResult.md). The service has no streaming RPC. The package is `axinfer.v1`. The server listens on `0.0.0.0:<port>` without TLS. The handler is [PipelineService-Infer](../grpc/PipelineService-Infer.md).

### Concurrency

Many calls can run at once. Concurrency behavior depends on the underlying runtime.

### Constraints

- The server accepts calls only in state `READY`.
- A dropped frame is not a gRPC error. The call returns `OK` and the result carries `status = DROPPED`.

## Signature

```proto
service AxInference {
  rpc Infer(InferRequest) returns (FrameResult);
}
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `request` | `InferRequest` | none | Yes | Encoded image and optional `request_id`. |

## Returns

A `FrameResult` with detections, classifications, or both.

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| `OK` | The call completed or the pipeline dropped the frame. `status` is `COMPLETE` or `DROPPED`. | Read `status` and `status_message`. |
| `UNAVAILABLE` | The server is not `READY`. | Retry later. |
| `DEADLINE_EXCEEDED` | No result arrived within `timeout_s`. | Retry or raise the server timeout. |
| `INTERNAL` | Decode failure or pipeline exception. | Check the image and the server log. |

## Usage Examples

### Basic

```python
import grpc
from axinfer.v1 import inference_pb2, inference_pb2_grpc

channel = grpc.insecure_channel("localhost:50051")
stub = inference_pb2_grpc.AxInferenceStub(channel)
req = inference_pb2.InferRequest(image_data=open("img.jpg", "rb").read(), request_id="r1")
res = stub.Infer(req, timeout=5)
```

## Edge Cases

- The result echoes `request_id` when the request sets it.
- A full decode queue returns `DROPPED` with `status_message` a queue-full message.

## Related APIs

| API | Relationship |
|---|---|
| [InferRequest](InferRequest.md) | Request message. |
| [FrameResult](FrameResult.md) | Response message. |
| [InferenceStatus](InferenceStatus.md) | Values of `FrameResult.status`. |

## Source Reference

- `proto/axinfer/v1/inference.proto::AxInference` (lines 97-100)
