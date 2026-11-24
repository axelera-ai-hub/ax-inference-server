# Pipeline nodes reference

## Overview
This area documents the C++ pipeline nodes, predicates and builder of the inference server. The builder reads a JSON spec and wires nodes into a graph. Each node receives `Frame` objects through `process()`. Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Architecture
```mermaid
flowchart LR
    Spec[JSON spec] --> Builder[PipelineBuilder]
    Builder --> Entry[entry_node]
    Entry --> Nodes[Nodes and predicates]
    Nodes --> Result[result_queue]
```

## Pages
| Page | Kind | Summary |
|---|---|---|
| [AxPipelineNode](AxPipelineNode.md) | class | Abstract base class of all pipeline nodes. |
| [QueueOccupancy](QueueOccupancy.md) | struct | Snapshot of a node's queue fill levels. |
| [Frame](Frame.md) | struct | Unit of work that flows through every node. |
| [FramePipelineExt](FramePipelineExt.md) | struct | Per-frame state for ROI iteration. |
| [Predicate](Predicate.md) | class | Abstract boolean test on a frame. |
| [MetaKeyExistsPredicate](MetaKeyExistsPredicate.md) | class | True when the frame's meta map has a key. |
| [KptsConfidencePredicate](KptsConfidencePredicate.md) | class | True when selected keypoints exceed a visibility threshold. |
| [PluginPredicate](PluginPredicate.md) | class | Predicate loaded from a shared library. |
| [InferenceNode](InferenceNode.md) | class | Runs a net with bounded queues and worker threads. |
| [FilterNodeConfig](FilterNodeConfig.md) | struct | Configuration of FilterNode. |
| [FilterNode](FilterNode.md) | class | Filters detections by class, score and size. |
| [RoiIterNodeConfig](RoiIterNodeConfig.md) | struct | Configuration of RoiIterNode. |
| [RoiIterNode](RoiIterNode.md) | class | Crops the next detected box per pass. |
| [RoiCollectNodeConfig](RoiCollectNodeConfig.md) | struct | Configuration of RoiCollectNode. |
| [RoiCollectNode](RoiCollectNode.md) | class | Renames per-ROI results and advances the ROI index. |
| [ConditionNode](ConditionNode.md) | class | Routes a frame to a then or else successor. |
| [LoopGuardNodeConfig](LoopGuardNodeConfig.md) | struct | Configuration of LoopGuardNode. |
| [LoopGuardNode](LoopGuardNode.md) | class | Decides whether an ROI loop repeats or exits. |
| [RenameNode](RenameNode.md) | class | Moves a meta entry to another key. |
| [BuiltPipeline](BuiltPipeline.md) | struct | Result of the builder: entry node, result queue and nodes. |
| [PipelineBuilder](PipelineBuilder.md) | class | Builds a node graph from a JSON spec. |
| [PipelineBuilder.build](PipelineBuilder.build.md) | function | Parses the spec and wires the nodes. |
| [try_push_for](try_push_for.md) | function | Pushes to a BlockingQueue with a timeout. |
| [join_with_timeout](join_with_timeout.md) | function | Joins a thread with a deadline. |

## Quick Example
```cpp
Ax::PipelineBuilder builder("pipeline.json", logger);
Ax::BuiltPipeline pipeline = builder.build();
pipeline.entry_node->process(frame);
```
