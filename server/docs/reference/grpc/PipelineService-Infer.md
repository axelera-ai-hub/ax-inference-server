# PipelineService::Infer

## Summary

`Infer` handles the `AxInference.Infer` RPC. It takes one encoded image and returns one `FrameResult`.

## Detailed Description

`PipelineService` implements the generated `AxInference::Service` interface inside `server/src/interface/grpc.cpp`. `GrpcServer` creates it. Clients reach it through the RPC described on the [AxInference](../proto/AxInference.md) page.

### Behavior

1. Return `UNAVAILABLE` unless the service state is `READY`.
2. Take a frame from the frame pool and copy `image_data` into it.
3. Register a promise for the frame id and push the frame into the decode queue.
4. If the push does not succeed within `imdecode_queue_timeout_ms`, answer `DROPPED` with `status_message` a queue-full message.
5. Wait up to `timeout_s` for the output worker to resolve the promise.
6. If the frame is marked dropped, answer `DROPPED` with the frame's `drop_reason`.
7. Otherwise fill the result from the frame meta and set `status` to `COMPLETE`.

The method sets `request_id` in the result whenever the request carries one. A decode worker decodes the image to `output_format` and calls the entry node. A decode failure reaches `Infer` as an exception and becomes `INTERNAL`.

### Result building

The result builder reads the frame `Ax::MetaMap` and chooses the output by meta type, not by key name.

| Meta source | Result field |
|---|---|
| First `AxMetaObjDetection` in the map | `FrameResult.detections`, with `class_id`, `label`, `score` and `bbox`. |
| Key `<prefix>_<i>` holding `AxMetaClassification` | `Detection.classifications` of detection `i`. |
| Key `<prefix>_<i>` holding `AxMetaKptsDetection` | `Detection.keypoints`, or `face_bbox` and `face_landmarks` for the role `face`. |
| Key `<prefix>_<i>` holding `AxMetaEmbeddings` | One `NamedEmbedding` with `key` set to the prefix. |
| Key `<prefix>_<i>` holding `AxMetaSegmentsDetection` | `Detection.segmentation`, a simplified polygon. |
| Top-level key `classifications` | `FrameResult.classifications`. |

The `meta_key_roles` map assigns the role `keypoints` or `face` to a prefix. A prefix without an entry has the role `keypoints`. Without an object detection, the builder creates detections from the first non-empty keypoint meta and the first non-empty segment meta. Coordinates add the ROI crop origin when the frame records one for the detection. Otherwise they add the detection box origin. The keypoint count comes from the meta shape and defaults to 17. The face landmark count defaults to 5. The segmentation mapping assumes a 640x640 letterboxed model input and a mask stride of 4.

### Concurrency

Many calls can run at once, limited by `max_streams`. Each call waits on its own promise. Concurrency behavior depends on the underlying runtime.

### Constraints

- The call accepts requests only in state `READY`.
- Each call reserves 50 MB for the encoded image buffer.

## Signature

```cpp
Status Infer(ServerContext *,
             const axinfer::v1::InferRequest *request,
             axinfer::v1::FrameResult *response) override
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `request` | `const axinfer::v1::InferRequest *` | none | Yes | Encoded image and optional `request_id`. |
| `response` | `axinfer::v1::FrameResult *` | none | Yes | Result the call fills. |

## Returns

A `grpc::Status`. `OK` means the call completed or dropped the frame. The `response.status` field tells which.

## Exceptions

| Code | Trigger | Recovery |
|---|---|---|
| `UNAVAILABLE` | State is not `READY`. Message `Server is <state>, please retry`. | Retry later. |
| `DEADLINE_EXCEEDED` | No result within `timeout_s`. Message `Timeout waiting for pipeline result`. | Retry or raise `--timeout`. |
| `INTERNAL` | Decode failure or pipeline exception. Message `Pipeline error: <reason>`. | Check the image and the server log. |

## Edge Cases

- A drop returns gRPC `OK` with `status = DROPPED`, not an error.
- A watchdog restart resolves pending requests as `DROPPED` with `status_message` `server restarted by watchdog`.
- A request with no detections and no classifications returns `COMPLETE` with empty lists.

## Related APIs

| API | Relationship |
|---|---|
| [AxInference](../proto/AxInference.md) | Service definition. |
| [FrameResult](../proto/FrameResult.md) | Response message. |
| [InferRequest](../proto/InferRequest.md) | Request message. |
| [GrpcServerConfig](GrpcServerConfig.md) | Supplies the timeouts and queue settings. |

## Source Reference

- `server/src/interface/grpc.cpp::PipelineService::Infer` (lines 627-700)
