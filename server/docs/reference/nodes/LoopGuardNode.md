# LoopGuardNode

## Overview
`Ax::LoopGuardNode` decides after each loop pass whether to repeat or leave the loop. The JSON spec uses `type: "loop_guard"`. The node queues frames and handles them on an internal dispatch thread.

## Attributes
This class has no public attributes. Pass a [LoopGuardNodeConfig](LoopGuardNodeConfig.md) to the constructor. Call `set_continue()` and `set_exit()` to set the successors.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Queues the frame. Drops and logs it if the queue stays full for `queue_timeout`. | This page |
| `stop()` | Stops the queue and joins the dispatch thread. Waits at most 5 seconds. | This page |
| `set_continue(PipelineCallback cb)` | Sets the continue successor. | This page |
| `set_exit(PipelineCallback cb)` | Sets the exit successor. | This page |
| `~LoopGuardNode()` | Calls `stop()` and swallows exceptions. | This page |

### Decision
The dispatch thread evaluates `until` (when not null) on each frame. It compares `Frame::pipeline_ext->roi_index` with `max_iters`. The frame goes to the exit callback when `until` is true or `roi_index >= max_iters`. Otherwise it goes to the continue callback. A dropped frame is not reported to the client.

`pipeline_ext` must be set on the frame.

## Initialization
```cpp
explicit LoopGuardNode(LoopGuardNodeConfig cfg);
```
The constructor starts the dispatch thread. The JSON node needs `continue_to` and `exit_to` (node ids). The builder fails if either is missing or unknown.

## Lifecycle
1. The constructor starts the dispatch thread.
2. `process()` feeds the queue.
3. `stop()` stops the queue and joins the thread, or abandons it after 5 seconds. See [join_with_timeout](join_with_timeout.md).

Callbacks run on the dispatch thread.

## Related Classes
| Class | Relationship |
|---|---|
| [RoiIterNode](RoiIterNode.md) | Starts each loop pass. |
| [RoiCollectNode](RoiCollectNode.md) | Advances `roi_index`. |
| [Predicate](Predicate.md) | Type of `until`. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/guard.h::Ax::LoopGuardNode` (lines 40-77), `server/src/nodes/guard.cpp::LoopGuardNode` (lines 11-32)
