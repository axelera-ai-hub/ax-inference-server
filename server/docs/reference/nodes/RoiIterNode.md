# RoiIterNode

## Overview
`Ax::RoiIterNode` starts or continues an ROI loop by cropping the next detected box from the frame. The JSON spec uses `type: "roi_iter"`. The `roi_index` in `Frame::pipeline_ext` selects the box for each pass.

## Attributes
This class has no public attributes. Pass a [RoiIterNodeConfig](RoiIterNodeConfig.md) to the constructor. Call `set_skip()` to set the successor for frames with no ROI left.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Crops the box at `roi_index` into `Frame::bgr` and forwards the frame. | This page |
| `set_skip(PipelineCallback cb)` | Sets the skip successor. | This page |

### Behavior of process
1. On the first pass (`roi_index` is 0) the node copies `Frame::bgr` to `roi_source_bgr`.
2. The node counts the boxes in the `AxMetaObjDetection` under `meta_key`. The count is 0 when the key is missing or holds another meta type.
3. If the count is 0 or `roi_index` has reached the count, the node restores `Frame::bgr` from `roi_source_bgr` and calls the skip callback.
4. Otherwise the node pads the box by `crop_padding`. It clamps the box to the source image with a minimum size of one pixel.
5. The node replaces `Frame::bgr` with a copy of the crop and records the rectangle in `roi_crop_rects`.
6. The node forwards the frame to the next node.

`pipeline_ext` must be set on the frame.

## Initialization
```cpp
explicit RoiIterNode(RoiIterNodeConfig cfg);
```
The JSON node needs `skip_to`, the id of the skip successor. The builder fails if it is missing or unknown.

## Lifecycle
The node has no threads. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [RoiCollectNode](RoiCollectNode.md) | Closes each loop pass. |
| [LoopGuardNode](LoopGuardNode.md) | Decides whether to loop again. |
| [FramePipelineExt](FramePipelineExt.md) | Holds the ROI state. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/iter.h::Ax::RoiIterNode` (lines 31-59), `server/src/nodes/iter.cpp::RoiIterNode::process` (lines 11-51)
