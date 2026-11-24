# RoiCollectNode

## Overview
`Ax::RoiCollectNode` closes one iteration of an ROI loop started by [RoiIterNode](RoiIterNode.md). The JSON spec uses `type: "roi_collect"`. It renames the per-ROI results so the next pass does not overwrite them.

## Attributes
This class has no public attributes. Pass a [RoiCollectNodeConfig](RoiCollectNodeConfig.md) to the constructor.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Renames the current ROI's results, advances `roi_index` and forwards the frame. | This page |

### Behavior of process
1. For each key in `cls_meta_keys`, the node moves the meta entry to `<key>_<roi_index>`. It skips keys that are absent.
2. The node increments `roi_index`.
3. The node counts the boxes in the `AxMetaObjDetection` under `det_meta_key`.
4. If `roi_index` has reached the count, the node restores `Frame::bgr` from `roi_source_bgr` and adds an `AxMetaBase` entry named `_roi_done` to `meta`.
5. The node forwards the frame to the next node.

`pipeline_ext` must be set on the frame.

## Initialization
```cpp
explicit RoiCollectNode(RoiCollectNodeConfig cfg);
```

## Lifecycle
The node has no threads. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [RoiIterNode](RoiIterNode.md) | Starts each loop pass. |
| [LoopGuardNode](LoopGuardNode.md) | Bounds the loop. |
| [FramePipelineExt](FramePipelineExt.md) | Holds `roi_index`. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/collect.h::Ax::RoiCollectNode` (lines 32-52), `server/src/nodes/collect.cpp::RoiCollectNode::process` (lines 10-35)
