# LoopGuardNodeConfig

## Overview
`Ax::LoopGuardNodeConfig` configures [LoopGuardNode](LoopGuardNode.md).

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `until` | `std::shared_ptr<Predicate>` | null | Predicate that ends the loop when true. May be null. |
| `max_iters` | `int` | 3 | The loop ends once `roi_index` reaches this value. |
| `dispatch_queue_depth` | `size_t` | 8 | Capacity of the internal queue. |
| `queue_timeout` | `std::chrono::milliseconds` | 2000 ms | Wait for queue space before the node drops a frame. |

## Methods
The struct has no methods.

## Initialization
The struct is an aggregate. `PipelineBuilder` reads these JSON fields.

| JSON field | Maps to | Default |
|---|---|---|
| `until` | `until` (a name from `predicates`, required) | none |
| `max_iters` | `max_iters` | 3 |
| `dispatch_queue_depth` | `dispatch_queue_depth` | 8 |
| `queue_timeout_ms` | `queue_timeout` | 2000 |

## Lifecycle
`LoopGuardNode` copies the config at construction.

## Related Classes
| Class | Relationship |
|---|---|
| [LoopGuardNode](LoopGuardNode.md) | Consumes the config. |
| [Predicate](Predicate.md) | Type of `until`. |

## Source Reference
`server/include/nodes/guard.h::Ax::LoopGuardNodeConfig` (lines 26-31), `server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502)
