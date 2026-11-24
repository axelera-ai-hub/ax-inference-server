# FilterNodeConfig

## Overview
`Ax::FilterNodeConfig` configures [FilterNode](FilterNode.md). A negative numeric value disables that criterion.

## Attributes
| Attribute | Type | Default | Description |
|---|---|---|---|
| `meta_key` | `std::string` | empty | Meta key of the detection result to filter. |
| `classes` | `std::vector<int>` | empty | Class ids to keep. Empty keeps all classes. |
| `min_score` | `float` | -1 | Minimum score to keep. Negative disables. |
| `max_score` | `float` | -1 | Maximum score to keep. Negative disables. |
| `min_width` | `int` | -1 | Minimum box width in pixels. Negative disables. |
| `min_height` | `int` | -1 | Minimum box height in pixels. Negative disables. |
| `top_k` | `int` | -1 | Maximum number of highest-scoring detections to keep. Negative disables. |
| `which` | `std::string` | `"all"` | Reduction after the thresholds: `all`, `highest_score` or `center`. |

## Methods
The struct has no methods.

## Initialization
The struct is an aggregate. `PipelineBuilder` fills it from the JSON node fields of the same names. `meta_key` is required. The builder reads the others only when present. Any `which` value other than `highest_score` or `center` keeps all survivors.

## Lifecycle
`FilterNode` copies the config at construction.

## Related Classes
| Class | Relationship |
|---|---|
| [FilterNode](FilterNode.md) | Consumes the config. |

## Source Reference
`server/include/nodes/filter.h::Ax::FilterNodeConfig` (lines 27-36)
