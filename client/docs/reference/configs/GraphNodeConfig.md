# GraphNodeConfig

## Overview

`GraphNodeConfig` is one node of a pipeline graph. One flat model covers every node type. The validator checks which optional fields each type requires. It does not reject fields that are irrelevant to the type.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| id | str | none | yes | none | Node id. Each id must be unique within the pipeline. The validator does not check this. |
| type | Literal | none | yes | See node types | Node kind. |
| net | str or None | `None` | type `net` | Must name an entry of `nets:` | Net to run. |
| meta_key | str or None | `None` | `mock_net`, `roi_iter` | none | Meta key read or written by the node. |
| classes | list[int] or None | `None` | no | none | Class ids. The model checks the type and passes the value to the server JSON. |
| min_score | float or None | `None` | no | none | Minimum score. The model checks the type and passes the value to the server JSON. |
| max_score | float or None | `None` | no | none | Maximum score. The model checks the type and passes the value to the server JSON. |
| min_width | int or None | `None` | no | none | Minimum box width. The model checks the type and passes the value to the server JSON. |
| min_height | int or None | `None` | no | none | Minimum box height. The model checks the type and passes the value to the server JSON. |
| top_k | int or None | `None` | no | none | Top-k count. The model checks the type and passes the value to the server JSON. |
| which | Literal or None | `all` | no | `highest_score`, `center` or `all` | Box selection mode. The model passes the value to the server JSON. |
| next | str or list[str] or None | `None` | no | Forbidden on `sink`. A list of 2 or more for `fan_out` | Successor node id or ids. |
| predicate | str or None | `None` | `condition` | Must name an entry of `predicates:` | Predicate to evaluate. |
| then | str or None | `None` | `condition` | Node id | Target when the predicate is true. |
| else_ | str or None | `None` | `condition` | Node id. YAML key `else` | Target when the predicate is false. |
| cases | dict[str, str] or None | `None` | `switch` | Keys must name predicates | Predicate name to target node id. |
| default | str or None | `None` | no | Node id | Fallback target of a `switch`. |
| until | str or None | `None` | `loop_guard` | Must name an entry of `predicates:` | Exit predicate. |
| continue_to | str or None | `None` | `loop_guard` | Node id | Loop-back target. |
| exit_to | str or None | `None` | `loop_guard` | Node id | Exit target. |
| max_iters | int | `3` | no | none | Iteration cap of a `loop_guard`. |
| dispatch_queue_depth | int or None | `None` | no | none | Queue depth. The model passes the value to the server JSON. |
| queue_timeout_ms | int or None | `None` | no | none | Queue timeout in ms. The model passes the value to the server JSON. |
| queue_depth | int or None | `None` | no | none | Queue depth. The model passes the value to the server JSON. |
| module | str or None | `None` | no | none | Module name. The model passes the value to the server JSON. |
| fn | str or None | `None` | no | none | Function name. The model passes the value to the server JSON. |
| so_path | str or None | `None` | `custom` | none | Plugin library path. |
| plugin_timeout_ms | int or None | `None` | no | none | Plugin timeout in ms. The model passes the value to the server JSON. |
| gather | str or None | `None` | no | `union` or `none` | Fan-in merge mode. The compiler sets `union` when unset. |
| fanin_timeout_ms | int or None | `None` | no | none | Fan-in timeout in ms. The compiler sets twice `flush_thres` when unset. |
| frames | list[Any] or None | `None` | `mock_net` | Non-empty | Canned results of a `mock_net`. |
| skip_to | str or None | `None` | `roi_iter` | Node id | Node to jump to. |
| det_meta_key | str or None | `None` | `roi_collect` | none | Detection meta key. |
| cls_meta_key | str or list[str] or None | `None` | `roi_collect` | none | Classification meta key or keys. |
| crop_padding | float | `0.0` | no | none | Crop padding. The model passes the value to the server JSON. |
| rename_from | str or None | `None` | `rename` | none | Source meta key. |
| rename_to | str or None | `None` | `rename` | none | Destination meta key. |

## Validators

| Target | Rule |
|---|---|
| `type: net` | Requires `net`. |
| `type: mock_net` | Requires a non-empty `frames` and a `meta_key`. |
| `type: sink` | Must not have `next`. |
| `type: condition` | Requires `predicate`, `then` and `else`. |
| `type: switch` | Requires a non-empty `cases`. |
| `type: fan_out` | Requires `next` as a list of at least 2 ids. |
| `type: fan_in` | `gather`, when set, must be `union` or `none`. |
| `type: loop_guard` | Requires `until`, `continue_to` and `exit_to`. |
| `type: custom` | Requires `so_path`. |
| `type: roi_iter` | Requires `meta_key` and `skip_to`. |
| `type: roi_collect` | Requires `det_meta_key` and `cls_meta_key`. |
| `type: rename` | Requires `rename_from` and `rename_to`. |

Node types: `net`, `filter`, `fan_out`, `fan_in`, `condition`, `switch`, `loop_guard`, `custom`, `sink`, `mock_net`, `roi_iter`, `roi_collect`, `rename`. The model accepts both `else` and `else_` as the key (`populate_by_name`).

## Example

```yaml
nodes:
  - id: det
    type: net
    net: detector
    next: out
  - id: out
    type: sink
```

## Related

| Page | Relationship |
|---|---|
| [PipelineGraphConfig](PipelineGraphConfig.md) | Holds the node list. |
| [NetConfig](NetConfig.md) | Target of `net`. |
| [PredicateConfig](PredicateConfig.md) | Target of `predicate`, `until` and `cases`. |

## Source Reference

- `client/configs/utils/config_schema.py::GraphNodeConfig` (lines 333-464)
