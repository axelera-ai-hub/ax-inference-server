# PredicateCompiler

## Overview

`PredicateCompiler` compiles an `expr` predicate to a shared library with g++. It writes `predicate_<name>.cpp` and `predicate_<name>.so` into the output directory.

## Attributes

This class exposes no public attributes.

## Methods

| Method | Summary | Page |
|---|---|---|
| `__init__(name, cfg, output_dir, sdk_root)` | Stores the predicate and build settings. | This page |
| `compile()` | Transpiles and builds the library. | [PredicateCompiler.compile](PredicateCompiler.compile.md) |

## Initialization

```python
PredicateCompiler(name: str, cfg: ExprPredicateConfig, output_dir: Path, sdk_root: str)
```

| Parameter | Type | Description |
|---|---|---|
| name | str | Predicate name, used for the output file names. |
| cfg | ExprPredicateConfig | Config holding `inputs` and `body`. |
| output_dir | Path | Directory for the generated `.cpp` and `.so` files. It must exist. |
| sdk_root | str | SDK root. The directory `operators/axstreamer/include` under it joins the include path. |

## Lifecycle

The constructor stores the arguments. `compile()` does all work. `PipelineCompiler` creates one instance per referenced expression predicate.

## Related Classes

| Class | Relationship |
|---|---|
| [ExprTranspiler](ExprTranspiler.md) | Produces the C++ source. |
| [PipelineCompiler](PipelineCompiler.md) | Calls this class. |
| [ExprPredicateConfig](../configs/ExprPredicateConfig.md) | Type of `cfg`. |

## Source Reference

- `client/compiler/predicate.py::PredicateCompiler` (lines 310-389)
