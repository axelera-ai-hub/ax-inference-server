# BoundingBox

## Overview

`BoundingBox` is an axis-aligned box in pixels. `Detection` uses it for `bbox`, `track_history` and `face_bbox`.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `x` | 1 | `uint32` | singular | Left edge. |
| `y` | 2 | `uint32` | singular | Top edge. |
| `w` | 3 | `uint32` | singular | Width. |
| `h` | 4 | `uint32` | singular | Height. |

## Related Messages

- [Detection](Detection.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::BoundingBox` (lines 9-14)
