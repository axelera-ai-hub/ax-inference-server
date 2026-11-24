# Point2D

## Overview

`Point2D` is a 2D point with an optional confidence. `Detection` uses it for keypoints, segmentation polygon points and face landmarks.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `x` | 1 | `float` | singular | X coordinate. |
| `y` | 2 | `float` | singular | Y coordinate. |
| `confidence` | 3 | `float` | optional | Confidence of the point. |

## Related Messages

- [Detection](Detection.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::Point2D` (lines 17-21)
