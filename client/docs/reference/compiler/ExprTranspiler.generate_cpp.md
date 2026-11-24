# ExprTranspiler.generate_cpp

## Summary

Generates the C++ source of the predicate plugin.

## Detailed Description

### Behavior

The method parses the body with `ast.parse` and checks every node against the allowed set. It translates the body to a fully parenthesised C++ expression. It declares each input as a `const` local read from the frame's meta map. The output exports `ax_create_predicate` and `ax_destroy_predicate`.

### Concurrency

The method has no side effects. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def generate_cpp(self) -> str
```

## Parameters

This function takes no parameters.

## Returns

`str`. A complete C++ translation unit.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| ValueError | The body has a syntax error, uses a forbidden construct, names an undeclared variable, chains comparisons, or an input helper is invalid. | Fix the expression or the input definition. |

## Usage Examples

### Basic

```python
import sys

sys.path.insert(0, 'client/compiler')

from predicate import ExprTranspiler

src = ExprTranspiler('many', {'n': "num_detections('det')"}, 'n > 3').generate_cpp()
```

## Edge Cases

- Integer arguments of `has_class` and `kpts_all_confident` must parse as integers.
- Float constants get an `f` suffix.

## Related APIs

| API | Relationship |
|---|---|
| [ExprTranspiler](ExprTranspiler.md) | Owning class. |
| [PredicateCompiler.compile](PredicateCompiler.compile.md) | Builds the source into a library. |

## Source Reference

- `client/compiler/predicate.py::ExprTranspiler.generate_cpp` (lines 240-307)
