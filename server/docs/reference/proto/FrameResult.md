# FrameResult

## Overview

`FrameResult` is the result for one image. `Infer` returns it.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `detections` | 1 | `Detection` | repeated | Detected objects. |
| `classifications` | 2 | `ClassScore` | repeated | Image-level classification results. |
| `request_id` | 3 | `string` | optional | Echo of `InferRequest.request_id`. |
| `status` | 4 | `InferenceStatus` | optional | Outcome of the request. |
| `status_message` | 5 | `string` | optional | Drop reason when `status` is `DROPPED`. |

## Related Messages

- [Detection](Detection.md)
- [ClassScore](ClassScore.md)
- [InferenceStatus](InferenceStatus.md)
- [InferRequest](InferRequest.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::FrameResult` (lines 73-88)
