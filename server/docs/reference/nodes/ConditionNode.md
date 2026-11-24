# ConditionNode

## Overview
`Ax::ConditionNode` sends each frame to a "then" or an "else" successor. The JSON spec uses `type: "condition"`. The node evaluates its [Predicate](Predicate.md) on the calling thread.

## Attributes
This class has no public attributes. The constructor takes the [Predicate](Predicate.md) that the node evaluates for every frame.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Forwards the frame to the then or else successor. Drops the frame if the chosen successor is unset. | This page |
| `set_next(PipelineCallback)` | Ignores the callback. | This page |
| `set_then(PipelineCallback cb)` | Sets the true successor. | This page |
| `set_else(PipelineCallback cb)` | Sets the false successor. | This page |

The node drops a frame without a log message when the chosen successor is unset.

## Initialization
```cpp
explicit ConditionNode(std::shared_ptr<Predicate> predicate);
```
The JSON node needs `predicate` (a name from `predicates`), `then` and `else` (node ids). The builder fails on an unknown predicate or node id. A `next` field in the JSON has no effect.

## Lifecycle
The node has no threads. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [Predicate](Predicate.md) | Condition type. |
| [LoopGuardNode](LoopGuardNode.md) | Other node that uses a predicate. |
| [AxPipelineNode](AxPipelineNode.md) | Base class. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/condition.h::Ax::ConditionNode` (lines 18-54)
