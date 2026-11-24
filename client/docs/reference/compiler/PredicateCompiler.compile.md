# PredicateCompiler.compile

## Summary

Transpiles the predicate and builds it into a shared library.

## Detailed Description

### Behavior

The method generates C++ with `ExprTranspiler` and writes `predicate_<name>.cpp`. It builds it with `g++-12` when available, otherwise `g++`, using `-std=c++20 -O2 -fPIC -shared`. Include paths are `server/include` in the repository, the SDK `operators/axstreamer/include` directory and the OpenCV flags. OpenCV flags come from `pkg-config --cflags opencv4`. If that fails, the method uses `/usr/include/opencv4` or `/usr/local/include/opencv4` when present.

### Concurrency

The method blocks while g++ runs. Concurrency behavior depends on the underlying runtime.

### Constraints

Requires g++ with C++20 support and the SDK headers.

## Signature

```python
def compile(self) -> Path
```

## Parameters

This function takes no parameters.

## Returns

`Path`. The path of `predicate_<name>.so`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| ValueError | The expression is invalid. | Fix the predicate `inputs` or `body`. |
| FileNotFoundError | `output_dir` does not exist, or no `g++` binary is on the path. | Create the directory or install g++. |
| RuntimeError | g++ exits with a non-zero status. The message includes the command and stderr. | Check the compiler output, the SDK path and the OpenCV headers. |

## Usage Examples

### Basic

```python
import sys
from pathlib import Path

sys.path.insert(0, 'client/compiler')

from predicate import PredicateCompiler

so_path = PredicateCompiler(name, expr_cfg, Path('out'), sdk_root).compile()
```

## Edge Cases

- The method overwrites existing files of the same name.
- A missing `output_dir` raises `FileNotFoundError` when the method writes the source file.

## Related APIs

| API | Relationship |
|---|---|
| [PredicateCompiler](PredicateCompiler.md) | Owning class. |
| [ExprTranspiler.generate_cpp](ExprTranspiler.generate_cpp.md) | Generates the source. |

## Source Reference

- `client/compiler/predicate.py::PredicateCompiler.compile` (lines 336-389)
