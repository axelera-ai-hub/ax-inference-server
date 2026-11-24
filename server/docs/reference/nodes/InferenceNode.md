# InferenceNode

## Overview
`Ax::InferenceNode` wraps an `AxInferenceNet` with bounded queues and two worker threads. The JSON spec uses `type: "net"`. Frames enter an input queue. A push thread feeds them to the net. Completed frames pass through a result queue to a drain thread that calls the next node.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `node_id` | `std::string` | none | Identifier used in log messages and drop reasons. |
| `props` | `const InferenceNetProperties &` | none | Model and device settings for the net. |
| `logger` | `Ax::Logger &` | none | Logger handed to the inference net. |
| `queue_timeout` | `std::chrono::milliseconds` | 2000 ms | Wait for space in the input queue before the node drops the frame. |
| `drop_sink` | `std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>>` | null | Queue that receives dropped frames. Null means log only. |
| `join_timeout` | `std::chrono::milliseconds` | 5000 ms | Per-thread wait during `stop()`. |
| `queue_depth` | `size_t` | 1 | Capacity of the input queue and the result queue. |
| `done_callback_timeout` | `std::chrono::milliseconds` | 50 ms | Wait for result queue space when the net completes a frame. |

`queue_timeout` applies only to the input queue in `process()`. The result queue wait uses `done_callback_timeout`. The node pushes a dropped frame to `drop_sink` with the timeout of the drop that triggered it.

## Methods
| Method | Summary | Page |
|---|---|---|
| `process(std::shared_ptr<Frame> frame)` | Queues the frame. Drops it if the input queue stays full for `queue_timeout`. | This page |
| `stop()` | Stops the queues, the threads and the net. Each join waits at most `join_timeout`. | This page |
| `queue_occupancy() const` | Returns used and total depth of both queues. | [QueueOccupancy](QueueOccupancy.md) |
| `~InferenceNode()` | Calls `stop()` and swallows exceptions. | This page |

### Drops
A drop logs a message to the `PIPELINE` log. If `drop_sink` is set, the node sets `Frame::dropped` to true. It sets `Frame::drop_reason` to `InferenceNode[<node_id>]: <reason>`. It then pushes the frame to `drop_sink`. The reason is `input_queue_ full` or `result_queue_ full`. If the push to `drop_sink` fails, the client sees the pipeline timeout.

### Push thread
The push thread reads from the input queue. It uses `Frame::video_buffer` when `has_video_buffer()` is true. Otherwise it wraps `Frame::bgr` as a BGR image. It skips a frame with neither and sends no report.

## Initialization
```cpp
InferenceNode(std::string node_id,
              const InferenceNetProperties &props,
              Ax::Logger &logger,
              std::chrono::milliseconds queue_timeout = std::chrono::milliseconds(2000),
              std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> drop_sink = nullptr,
              std::chrono::milliseconds join_timeout = std::chrono::milliseconds(5000),
              size_t queue_depth = 1,
              std::chrono::milliseconds done_callback_timeout = std::chrono::milliseconds(50));
```
The constructor creates both queues and the net and starts both threads.

`PipelineBuilder` sets these values from the node's JSON.

| JSON field | Effect |
|---|---|
| `net` | Name of an entry in `nets`. Required. |
| `queue_timeout_ms` | Sets `queue_timeout`. Default 2000. |
| `queue_depth` | Sets `queue_depth`. Default is `max(1, num_children)` of the replica. |

The builder passes the pipeline result queue as `drop_sink`. It uses 5000 ms for `join_timeout`. It leaves `done_callback_timeout` at 50 ms. When a net has more than one replica, each `InferenceNode` is named `<id>_replica<N>` and a round-robin group routes frames among them.

## Lifecycle
1. The constructor starts the push thread and the drain thread.
2. `process()` feeds the input queue.
3. The net completion callback pushes the frame to the result queue.
4. The drain thread calls the callback set by `set_next()`.
5. `stop()` stops the input queue, joins the push thread, stops the net on a helper thread, stops the result queue and joins the drain thread.

A thread that misses its join timeout is abandoned and a message is logged. See [join_with_timeout](join_with_timeout.md). The net completion callback runs on the net's thread.

## Related Classes
| Class | Relationship |
|---|---|
| [AxPipelineNode](AxPipelineNode.md) | Base class. |
| [QueueOccupancy](QueueOccupancy.md) | Return type of `queue_occupancy()`. |
| [try_push_for](try_push_for.md) | Bounded push used for every queue. |
| [PipelineBuilder](PipelineBuilder.md) | Constructs the node. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/nodes/inference.h::Ax::InferenceNode` (lines 26-103), `server/src/nodes/inference.cpp::InferenceNode` (lines 12-68), `server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502)
