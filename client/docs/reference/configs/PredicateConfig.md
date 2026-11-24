# PredicateConfig

## Overview

`PredicateConfig` is a type alias for `Union[BuiltinPredicateConfig, ExprPredicateConfig, PluginPredicateConfig]`. `ServerConfig.predicates` maps predicate names to this union. Pydantic selects the variant from the `type` value.

## Fields

The alias has no fields. Each variant defines its own.

| Variant | Selected by | Page |
|---|---|---|
| `BuiltinPredicateConfig` | `type` is a built-in name | [BuiltinPredicateConfig](BuiltinPredicateConfig.md) |
| `ExprPredicateConfig` | `type: expr` | [ExprPredicateConfig](ExprPredicateConfig.md) |
| `PluginPredicateConfig` | `type: plugin` | [PluginPredicateConfig](PluginPredicateConfig.md) |

## Validators

This alias has no validators. Each variant defines its own.

## Example

```yaml
predicates:
  always:
    type: always_true
  crowded:
    type: expr
    inputs: {n: "num_detections('det')"}
    body: "n > 3"
```

## Related

| Page | Relationship |
|---|---|
| [ServerConfig](ServerConfig.md) | Holds the named predicates. |
| [GraphNodeConfig](GraphNodeConfig.md) | Nodes refer to predicates by name. |

## Source Reference

- `client/configs/utils/config_schema.py::PredicateConfig` (lines 269-269)
