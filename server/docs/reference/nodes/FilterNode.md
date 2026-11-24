# FilterNode

## Overview
`Ax::FilterNode` removes detections from a meta entry that fail the configured criteria. The JSON spec uses `type: "filter"`. It supports object, keypoint and segment detections. The filtered result replaces the original meta entry under the same key.

## Attributes
This class has no public attributes. Pass a [FilterNodeConfig](FilterNodeConfig.md) to the constructor.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Filters the detections under `meta_key` and forwards the frame. | This page |

### Selection order
1. Keep detections whose class is in `classes`, when `classes` is not empty.
2. Apply `min_score`, `max_score`, `min_width` and `min_height`.
3. Apply `which`. `highest_score` keeps the best detection. `center` keeps the detection whose box centre is closest to the image centre. `center` is skipped when `Frame::bgr` is empty.
4. Apply `top_k`. The node sorts and truncates only when `top_k >= 0` and the survivors exceed `top_k`. It then sorts the survivors by descending score and keeps the first `top_k`.

If `meta_key` is missing or its meta is not an `AxMetaBbox`, the node stores an empty `AxMetaObjDetection` under the key. If the meta is an `AxMetaBbox` of a type other than object, keypoint or segment detection, the node leaves it unchanged. The node then forwards the frame to the next node when one is set.

## Initialization
```cpp
explicit FilterNode(FilterNodeConfig cfg);
```

## Lifecycle
The node has no threads. `process()` runs on the calling thread. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [AxPipelineNode](AxPipelineNode.md) | Base class. |
| [FilterNodeConfig](FilterNodeConfig.md) | Configuration. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/filter.h::Ax::FilterNode` (lines 44-67), `server/src/nodes/filter.cpp::FilterNode::process` (lines 188-212)
