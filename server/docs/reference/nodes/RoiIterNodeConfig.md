# RoiIterNodeConfig

## Overview
`Ax::RoiIterNodeConfig` configures [RoiIterNode](RoiIterNode.md).

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `meta_key` | `std::string` | empty | Meta key of the object detection result that defines the ROIs. |
| `crop_padding` | `float` | 0 | Padding on each side of the box, as a fraction of box width and height. |

## Methods
The struct has no methods.

## Initialization
The struct is an aggregate. `PipelineBuilder` reads `meta_key` (required) and `crop_padding` (optional) from the JSON node.

## Lifecycle
`RoiIterNode` copies the config at construction.

## Related Classes
| Class | Relationship |
|---|---|
| [RoiIterNode](RoiIterNode.md) | Consumes the config. |

## Source Reference
`server/include/nodes/iter.h::Ax::RoiIterNodeConfig` (lines 19-22)
