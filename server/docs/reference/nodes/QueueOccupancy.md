# QueueOccupancy

## Overview
`Ax::AxPipelineNode::QueueOccupancy` is a snapshot of a node's queue fill levels. A node returns it from `queue_occupancy()`. Callers use it for periodic statistics.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `node_id` | `std::string` | empty | Identifier of the reporting node. |
| `input_used` | `size_t` | 0 | Items currently in the input queue. |
| `input_depth` | `size_t` | 0 | Capacity of the input queue. |
| `result_used` | `size_t` | 0 | Items currently in the result queue. |
| `result_depth` | `size_t` | 0 | Capacity of the result queue. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `AxPipelineNode::queue_occupancy() const` | Returns the snapshot, or `std::nullopt` for nodes without queues. | [AxPipelineNode](AxPipelineNode.md) |

## Initialization
The struct is an aggregate with default member initializers. `InferenceNode::queue_occupancy()` fills it while it holds each queue's mutex. It sets `node_id` to the node's own id, which includes the `_replica<N>` suffix for replicas.

## Lifecycle
The snapshot is a value. It does not update after `queue_occupancy()` returns.

## Related Classes
| Class | Relationship |
|---|---|
| [AxPipelineNode](AxPipelineNode.md) | Declares the struct and the virtual method. |
| [InferenceNode](InferenceNode.md) | The only node in this area that overrides `queue_occupancy()`. |

## Source Reference
`server/include/pipeline/node.h::Ax::AxPipelineNode::QueueOccupancy` (lines 52-58), `server/src/nodes/inference.cpp::InferenceNode::queue_occupancy` (lines 116-131)
