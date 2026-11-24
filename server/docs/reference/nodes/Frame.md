# Frame

## Overview
`Ax::Frame` is the unit of work that flows through every pipeline node. It holds one image request with its decoded pixels, inference metadata and drop state. The gRPC layer reuses frames and resets `meta`, `id`, `is_dummy`, `encoded`, `net_idx`, the timestamps, `dropped` and `drop_reason` on acquire.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `bgr` | `cv::Mat` | empty | Decoded image in BGR order. ROI nodes temporarily replace it with a crop. |
| `video_buffer` | `Ax::VideoBuffer` | empty | Decoder output buffer. Valid only when `has_video_buffer()` is true. |
| `meta` | `Ax::MetaMap` | empty | Inference results keyed by meta name. |
| `id` | `int` | 0 | Request identifier assigned by the gRPC layer. |
| `is_dummy` | `bool` | false | Marks a filler frame instead of a real request. |
| `encoded` | `std::shared_ptr<std::vector<uint8_t>>` | null | Compressed request image bytes. Released after decoding. |
| `net_idx` | `int` | -1 | Index of the net replica handling the frame. -1 means unassigned. |
| `start_time` | `std::chrono::high_resolution_clock::time_point` | unset | Set when the request is received. |
| `end_time` | `std::chrono::high_resolution_clock::time_point` | unset | Set when the result is ready. Used for latency. |
| `pipeline_ext` | `std::shared_ptr<FramePipelineExt>` | null | Per-frame state for ROI iteration. See [FramePipelineExt](FramePipelineExt.md). |
| `dropped` | `bool` | false | True when a node discarded the frame. |
| `drop_reason` | `std::string` | empty | Reason text when `dropped` is true. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `has_video_buffer() const` | Returns true when `video_buffer` holds a valid decoder buffer. | This page |

## Initialization
`Frame` is an aggregate with default member initializers. The gRPC layer creates and pools frames.

## Lifecycle
The gRPC layer acquires a frame and fills it. Nodes read and modify it through `process()`. A terminal node or a drop pushes it to the result queue. The layer then returns it to the pool.

## Related Classes
| Class | Relationship |
|---|---|
| [FramePipelineExt](FramePipelineExt.md) | Type of `pipeline_ext`. |
| [AxPipelineNode](AxPipelineNode.md) | Nodes receive `std::shared_ptr<Frame>`. |
| [Predicate](Predicate.md) | Evaluates a `const Frame &`. |

## Source Reference
`server/include/pipeline/frame.h::Ax::Frame` (lines 41-59)
