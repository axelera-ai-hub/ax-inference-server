# BuiltinPredicateConfig

## Overview

`BuiltinPredicateConfig` is a predicate that the server's built-in set implements. The `type` field selects the built-in. The model keeps any extra keys as that predicate's parameters.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| type | Literal | none | yes | One of the built-in names below | Selects the built-in predicate. |
| (extra keys) | any | none | no | Accepted by `extra: allow` | Parameters of the selected predicate. |

## Validators

This model has no validators.

Allowed `type` values: `num_detections_gt`, `num_detections_lt`, `num_detections_eq`, `max_score_gt`, `max_score_lt`, `class_present`, `meta_key_exists`, `loop_iter_gte`, `always_true`, `always_false`, `and`, `or`, `not`, `top_class_is`, `top_class_score_gt`, `top_class_score_lt`, `kpts_conf_gt`.

The parameter names for each built-in are defined by the server. Behavior inferred from code inspection.

## Example

```yaml
predicates:
  always:
    type: always_true
```

## Related

| Page | Relationship |
|---|---|
| [PredicateConfig](PredicateConfig.md) | Union that includes this model. |
| [ServerConfig](ServerConfig.md) | Holds the named predicates. |

## Source Reference

- `client/configs/utils/config_schema.py::BuiltinPredicateConfig` (lines 205-223)
