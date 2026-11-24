# PipelineGraphConfig

## Overview

`PipelineGraphConfig` is the node graph of one pipeline. It holds the entry node id and the list of nodes. Its validator checks the graph structure.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| entry | str | none | yes | Must be the id of a node | Id of the first node. |
| nodes | list[GraphNodeConfig] | none | yes | See validators | All nodes of the graph. |

## Validators

| Target | Rule |
|---|---|
| entry | Must name a node. |
| references | Every node id in `next`, `then`, `else`, `continue_to`, `exit_to`, `default`, `skip_to` and `cases` values must exist. |
| sinks | Exactly one node must have type `sink`. |
| reachability | Every node must be reachable from `entry`. |
| cycles | The graph must have no cycle, except the `loop_guard` to `continue_to` edge. |

## Example

```yaml
graph:
  entry: det
  nodes:
    - {id: det, type: net, net: detector, next: out}
    - {id: out, type: sink}
```

## Related

| Page | Relationship |
|---|---|
| [GraphNodeConfig](GraphNodeConfig.md) | Element type. |
| [PipelineConfig](PipelineConfig.md) | Holds this model as `graph`. |

## Source Reference

- `client/configs/utils/config_schema.py::PipelineGraphConfig` (lines 547-583)
