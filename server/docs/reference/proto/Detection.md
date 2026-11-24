# Detection

## Overview

`Detection` is one detected object with optional per-object attributes. Field numbers 12 and 13 and the names `embedding` and `reid_embedding` are reserved.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `class_id` | 1 | `uint32` | singular | Class index. |
| `label` | 2 | `string` | singular | Class name. |
| `score` | 3 | `float` | singular | Detection score. |
| `bbox` | 4 | `BoundingBox` | singular | Box in pixels. |
| `classifications` | 5 | `ClassScore` | repeated | Per-object classification results. |
| `keypoints` | 6 | `Point2D` | repeated | Pose keypoints. |
| `segmentation` | 7 | `Point2D` | repeated | Segmentation polygon points. |
| `track_id` | 8 | `string` | optional | Tracker identity. |
| `track_history` | 9 | `BoundingBox` | repeated | Recent boxes of the track. |
| `face_bbox` | 10 | `BoundingBox` | optional | Face box associated with the detection. |
| `face_landmarks` | 11 | `Point2D` | repeated | Face landmarks. |
| `embeddings` | 14 | `NamedEmbedding` | repeated | Feature vectors identified by key. |

## Related Messages

- [BoundingBox](BoundingBox.md)
- [Point2D](Point2D.md)
- [ClassScore](ClassScore.md)
- [NamedEmbedding](NamedEmbedding.md)
- [FrameResult](FrameResult.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::Detection` (lines 37-64)
