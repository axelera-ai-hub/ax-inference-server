# BuiltPipeline

## Overview
`Ax::BuiltPipeline` is the result of `PipelineBuilder::build()`. It holds a wired node graph that is ready to receive frames.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `entry_node` | `std::shared_ptr<AxPipelineNode>` | null | Node that receives frames submitted to the pipeline. |
| `result_queue` | `std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>>` | null | Queue that the terminal nodes push finished or dropped frames into. |
| `all_nodes` | `std::vector<std::shared_ptr<AxPipelineNode>>` | empty | Every node in spec order. Used for `stop()` and `queue_occupancy()` sweeps. |
| `pipeline_depth` | `int` | 0 | Frames to keep in flight. 0 when the spec does not set it. |

`pipeline_depth` is `global.pipeline_depth` from the spec. The builder multiplies it by the largest replica count of any net when that count is above 1.

## Methods
The struct has no methods.

## Initialization
`PipelineBuilder::build()` returns the struct by value.

## Lifecycle
The caller submits frames to `entry_node`. It reads finished frames from `result_queue`. At shutdown it calls `stop()` on the nodes in `all_nodes` in reverse order.

## Related Classes
| Class | Relationship |
|---|---|
| [PipelineBuilder](PipelineBuilder.md) | Produces the struct. |
| [AxPipelineNode](AxPipelineNode.md) | Type of the nodes. |

## Source Reference
`server/include/pipeline/builder.h::Ax::BuiltPipeline` (lines 29-34)
