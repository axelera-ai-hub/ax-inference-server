# PipelineBuilder::build

## Summary
`build()` reads the JSON spec, creates every predicate and node, wires the nodes and returns a `BuiltPipeline`.

## Detailed Description
### Behavior
The spec has these top-level keys.

| Key | Required | Description |
|---|---|---|
| `nets` | No | Object of name to `{axnet_path, axnet_config}`. |
| `global` | Yes | Object with optional `result_queue_depth` and `pipeline_depth`. |
| `predicates` | No | Object of name to `{type, ...}`. See [Predicate](Predicate.md). |
| `nodes` | Yes | Array of node objects. Each has `id` and `type`. |
| `entry` | Yes | Id of the node that receives decoded frames. |

The builder creates one node for each `type`.

| `type` | Node | Type-specific fields |
|---|---|---|
| `net` | [InferenceNode](InferenceNode.md) | `net`, `queue_depth`, `queue_timeout_ms` |
| `sink` | Terminal node | none |
| `filter` | [FilterNode](FilterNode.md) | `meta_key`, `classes`, `min_score`, `max_score`, `min_width`, `min_height`, `top_k`, `which` |
| `roi_iter` | [RoiIterNode](RoiIterNode.md) | `meta_key`, `crop_padding`, `skip_to` |
| `roi_collect` | [RoiCollectNode](RoiCollectNode.md) | `det_meta_key`, `cls_meta_key` |
| `condition` | [ConditionNode](ConditionNode.md) | `predicate`, `then`, `else` |
| `rename` | [RenameNode](RenameNode.md) | `rename_from`, `rename_to` |
| `loop_guard` | [LoopGuardNode](LoopGuardNode.md) | `until`, `max_iters`, `dispatch_queue_depth`, `queue_timeout_ms`, `continue_to`, `exit_to` |

The `sink` node pushes each frame to the result queue. It waits at most 2000 ms for space. After that it drops the frame and logs a message.

The builder wires the nodes in a second pass, so forward references resolve. The `next` key sets the successor through `set_next()`. If `next` is an array, only the first entry is used. The keys `skip_to`, `continue_to`, `exit_to`, `then` and `else` set the node-specific successors.

Net handling:

- The builder reads each net with `read_inferencenet_properties` and calls `axr_list_devices`.
- It parses `axnet_config` into one entry per device group. Each entry sets `devices` and `num_children` for one replica.
- A net with more than one replica creates one `InferenceNode` per replica. A round-robin group distributes frames in order.
- The node queue depth is `queue_depth` from the node, or `max(1, num_children)`.

Queue depth and pipeline depth:

- `result_queue_depth` is `global.result_queue_depth`, or `max(2 * nodes.size(), 16)`.
- `pipeline_depth` is `global.pipeline_depth` (0 when absent), multiplied by the largest replica count when that count is above 1.

### Concurrency
`build()` sets the environment variable `GRPC_AXNET_CONFIG` while it reads a net and creates its nodes. It restores the previous value afterward. The change affects the whole process, so do not call `build()` concurrently with other code that reads this variable. Node threads start during `build()`.

### Constraints
The spec must contain `global`, `nodes` and `entry`. The spec needs at least one Axelera device when `nets` is not empty.

## Signature
```cpp
BuiltPipeline PipelineBuilder::build();
```

## Parameters
The method takes no parameters. It reads the spec file whose path was passed to the constructor.

## Returns
A [BuiltPipeline](BuiltPipeline.md) with the entry node, the result queue, all nodes in spec order and the pipeline depth.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `std::runtime_error` | nlohmann/json is unavailable at compile time. | Rebuild with `nlohmann-json3-dev`. |
| `std::runtime_error` | The spec file cannot be opened. | Fix `spec_path`. |
| `std::runtime_error` | The spec is not valid JSON. | Fix the JSON. |
| `std::runtime_error` | `nets` is set and no Axelera device is found. | Connect a device. |
| `std::runtime_error` | A node references an unknown net, predicate or node id. | Fix the reference. |
| `std::out_of_range` | `unordered_map::at` finds no entry, for example an unknown `entry` id. | Fix the reference. |
| `std::runtime_error` | A node or predicate type is unsupported. | Use a supported `type`. |
| `nlohmann::json::exception` | A required key is missing or has the wrong type. | Fix the spec. |

Behavior inferred from code inspection for the `nlohmann::json::exception` row.

## Usage Examples
### Basic
```cpp
Ax::PipelineBuilder builder("pipeline.json", logger);
Ax::BuiltPipeline pipeline = builder.build();
pipeline.entry_node->process(frame);
auto done = pipeline.result_queue->wait_one();
```
`wait_one()` is the `BlockingQueue` method used by `InferenceNode`.

## Edge Cases
- An empty `nets` object skips device discovery.
- An empty `axnet_config` yields one replica with the base properties.
- A `next` array uses only its first entry.
- An entry id that is not in `nodes` throws from `std::unordered_map::at`.

## Related APIs
| API | Relationship |
|---|---|
| [PipelineBuilder](PipelineBuilder.md) | Owning class. |
| [BuiltPipeline](BuiltPipeline.md) | Return type. |
| [InferenceNode](InferenceNode.md) | Created for `type: "net"`. |

## Source Reference
`server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502), `server/include/pipeline/builder.h::Ax::PipelineBuilder::build` (lines 62-62)
