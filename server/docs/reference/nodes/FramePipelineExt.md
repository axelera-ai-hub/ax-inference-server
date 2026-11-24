# FramePipelineExt

## Overview
`Ax::FramePipelineExt` holds the per-frame bookkeeping for ROI iteration. `RoiIterNode`, `RoiCollectNode` and `LoopGuardNode` read and write it through `Frame::pipeline_ext`. These nodes dereference `pipeline_ext` without a null check, so the caller must set it before the frame reaches them.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `roi_crop_rects` | `std::unordered_map<int, cv::Rect>` | empty | Crop rectangle used for each ROI, keyed by ROI index. |
| `roi_source_bgr` | `cv::Mat` | empty | Full-size copy of the image, kept while `Frame::bgr` holds a crop. |
| `roi_index` | `int` | 0 | Index of the ROI in process. |

## Methods
The struct has no methods.

## Initialization
The struct is an aggregate with default member initializers. `RoiIterNode` stores `roi_source_bgr` when `roi_index` is 0.

## Lifecycle
`RoiIterNode` writes `roi_crop_rects` and reads `roi_index`. `RoiCollectNode` advances `roi_index`. `LoopGuardNode` compares `roi_index` with `max_iters`.

## Related Classes
| Class | Relationship |
|---|---|
| [Frame](Frame.md) | Owns the `pipeline_ext` pointer. |
| [RoiIterNode](RoiIterNode.md) | Crops the ROI at `roi_index`. |
| [RoiCollectNode](RoiCollectNode.md) | Advances `roi_index`. |
| [LoopGuardNode](LoopGuardNode.md) | Ends the loop on `roi_index`. |

## Source Reference
`server/include/pipeline/frame_flags.h::Ax::FramePipelineExt` (lines 18-24)
