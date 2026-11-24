# ExprPredicateConfig

## Overview

`ExprPredicateConfig` is a predicate written as a restricted Python expression. `client/compiler/predicate.py` compiles it to C++ and builds a shared library.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| type | Literal['expr'] | none | yes | Must be `expr` | Selects this model. |
| inputs | dict[str, str] | none | yes | At least one entry | Variable name to helper call, for example `num_detections('det')`. |
| body | str | none | yes | Not blank | Expression over the input variables. |

## Validators

| Target | Rule |
|---|---|
| model | `inputs` must not be empty and `body` must not be blank. |

## Example

```yaml
predicates:
  crowded:
    type: expr
    inputs:
      n: "num_detections('det')"
    body: "n > 3"
```

## Related

| Page | Relationship |
|---|---|
| [ExprTranspiler](../compiler/ExprTranspiler.md) | Translates the expression. |
| [PredicateCompiler](../compiler/PredicateCompiler.md) | Builds the library. |
| [PredicateConfig](PredicateConfig.md) | Union that includes this model. |

## Source Reference

- `client/configs/utils/config_schema.py::ExprPredicateConfig` (lines 226-246)
