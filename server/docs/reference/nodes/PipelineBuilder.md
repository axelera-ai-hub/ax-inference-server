# PipelineBuilder

## Overview
`Ax::PipelineBuilder` constructs a [BuiltPipeline](BuiltPipeline.md) from a JSON spec file. The spec lists nets, predicates and nodes. The builder creates the nodes and wires them. `build()` requires nlohmann/json at compile time. Without it, `build()` throws at runtime.

## Attributes
This class has no public attributes. The constructor takes the spec path and a `Ax::Logger` reference. The logger must outlive the builder.

## Methods
| Method | Summary | Page |
|---|---|---|
| `PipelineBuilder(std::string spec_path, Ax::Logger &logger)` | Takes the spec path and the logger. The spec is read in `build()`. | This page |
| `build()` | Parses the spec, creates and wires the nodes. | [PipelineBuilder.build](PipelineBuilder.build.md) |

## Initialization
```cpp
PipelineBuilder(std::string spec_path, Ax::Logger &logger);
```

## Lifecycle
1. Construct the builder with the spec path.
2. Call `build()` once to get a `BuiltPipeline`.

## Related Classes
| Class | Relationship |
|---|---|
| [BuiltPipeline](BuiltPipeline.md) | Return type of `build()`. |
| [AxPipelineNode](AxPipelineNode.md) | Base class of the created nodes. |
| [Predicate](Predicate.md) | Created from the `predicates` object. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/pipeline/builder.h::Ax::PipelineBuilder` (lines 42-67), `server/src/pipeline/builder.cpp::PipelineBuilder` (lines 160-162)
