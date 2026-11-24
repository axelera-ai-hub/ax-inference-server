# AxPipelineNode

## Overview
`Ax::AxPipelineNode` is the abstract base class of all pipeline nodes. A node receives frames through `process()` and forwards them to the callback set by `set_next()`. The header also defines the `PipelineCallback` alias and the nested struct [QueueOccupancy](QueueOccupancy.md).

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `PipelineCallback` | `std::function<void(std::shared_ptr<Frame>)>` | Alias for a callback that hands a frame to the next stage. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Pure virtual. Handles one frame. | This page |
| `set_next(PipelineCallback cb)` | Virtual. Sets the callback that receives this node's output frames. | This page |
| `stop()` | Virtual. Stops internal threads and queues. The default does nothing. | This page |
| `queue_occupancy()` | Virtual. Returns a `std::optional<QueueOccupancy>`. The default returns `std::nullopt`. | [QueueOccupancy](QueueOccupancy.md) |

## Initialization
The class is abstract and has a virtual default destructor. A derived class implements `process()`. `PipelineBuilder` calls `set_next()` while it wires the graph.

## Lifecycle
1. The builder constructs the node.
2. The builder calls `set_next()` and any node-specific setters.
3. The pipeline calls `process()` for each frame.
4. The server calls `stop()` at shutdown.

`ConditionNode` overrides `set_next()` to ignore the callback. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [InferenceNode](InferenceNode.md) | Derived node that runs a model. |
| [PipelineBuilder](PipelineBuilder.md) | Creates and wires nodes. |
| [Frame](Frame.md) | Unit of work passed to `process()`. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/pipeline/node.h::Ax::AxPipelineNode` (lines 24-69), `server/include/pipeline/node.h::Ax::PipelineCallback` (lines 16-16)
