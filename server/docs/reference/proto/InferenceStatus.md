# InferenceStatus

## Overview

`InferenceStatus` is the outcome of a request. `FrameResult.status` uses it.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `COMPLETE` | 0 | enum value | n/a | The pipeline processed the frame. |
| `DROPPED` | 1 | enum value | n/a | The pipeline discarded the frame. `FrameResult.status_message` holds the reason. |

## Related Messages

- [FrameResult](FrameResult.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::InferenceStatus` (lines 67-70)
