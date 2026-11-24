# ExprTranspiler

## Overview

`ExprTranspiler` translates an `expr` predicate into C++ source. The predicate has named inputs and a Python boolean expression. Each input maps a variable name to a helper call. The body is a restricted Python expression over those variables. `generate_cpp()` returns a translation unit that defines an `Ax::Predicate` plugin.

## Attributes

This class exposes no public attributes.

## Methods

| Method | Summary | Page |
|---|---|---|
| `__init__(name, inputs, body)` | Stores the predicate definition. | This page |
| `generate_cpp()` | Returns the C++ source. | [ExprTranspiler.generate_cpp](ExprTranspiler.generate_cpp.md) |

## Initialization

```python
ExprTranspiler(name: str, inputs: dict[str, str], body: str)
```

| Parameter | Type | Description |
|---|---|---|
| name | str | Predicate name. Characters other than letters, digits and `_` become `_` in the C++ class name. |
| inputs | dict[str, str] | Variable name to helper call, for example `{'n': "num_detections('det')"}`. |
| body | str | Python expression over the input variables. |

Supported input helpers:

| Helper | C++ type | Meaning |
|---|---|---|
| `num_detections('key')` | int | Number of boxes in the meta entry. |
| `max_score('key')` | float | Highest box score, or 0 when empty. |
| `meta_exists('key')` | bool | The meta entry exists. |
| `has_class('key', class_id)` | bool | A box has the class id. |
| `kpts_all_confident('key', min_conf, i0, i1, i2)` | bool | Keypoints i0, i1 and i2 all have visibility above `min_conf`. |

The body allows constants, input names, `and`, `or`, `not` and unary `+` and `-`. It also allows binary `+ - * /` and single comparisons (`> < >= <= == !=`). Chained comparisons are rejected.

## Lifecycle

The object holds no state beyond its arguments. Call `generate_cpp()` as often as needed.

## Related Classes

| Class | Relationship |
|---|---|
| [PredicateCompiler](PredicateCompiler.md) | Compiles the generated source. |
| [ExprPredicateConfig](../configs/ExprPredicateConfig.md) | Config model that supplies `inputs` and `body`. |

## Source Reference

- `client/compiler/predicate.py::ExprTranspiler` (lines 100-307)
