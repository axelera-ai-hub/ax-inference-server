# InferRequest

## Overview

`InferRequest` carries one image to run through the pipeline.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `image_data` | 1 | `bytes` | singular | Encoded image, for example JPEG or PNG. |
| `request_id` | 2 | `string` | optional | Caller-chosen id, echoed in the result. |

## Related Messages

- [FrameResult](FrameResult.md)
- [AxInference](AxInference.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::InferRequest` (lines 91-94)
