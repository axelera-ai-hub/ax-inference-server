# RoiCollectNodeConfig

## Overview
`Ax::RoiCollectNodeConfig` configures [RoiCollectNode](RoiCollectNode.md).

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `det_meta_key` | `std::string` | empty | Meta key of the detection result that defines the ROIs. |
| `cls_meta_keys` | `std::vector<std::string>` | empty | Meta keys of per-ROI results to rename with an ROI-index suffix. |

## Methods
The struct has no methods.

## Initialization
The struct is an aggregate. In the JSON node, `det_meta_key` is required. `cls_meta_key` is required and accepts a string or an array of strings. The builder stores a single string as a one-element list.

## Lifecycle
`RoiCollectNode` copies the config at construction.

## Related Classes
| Class | Relationship |
|---|---|
| [RoiCollectNode](RoiCollectNode.md) | Consumes the config. |

## Source Reference
`server/include/nodes/collect.h::Ax::RoiCollectNodeConfig` (lines 20-23), `server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502)
