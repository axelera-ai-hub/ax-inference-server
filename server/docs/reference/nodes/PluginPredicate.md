# PluginPredicate

## Overview
`Ax::PluginPredicate` is a [Predicate](Predicate.md) implemented by a shared library that it loads with `dlopen`. The JSON spec uses `type: "plugin"` with the field `so_path`.

## Attributes
This class has no public attributes.

## Methods
| Method | Summary | Page |
|---|---|---|
| `eval(const Frame &frame) const` | Forwards to the plugin's `eval()`. | [Predicate](Predicate.md) |
| `PluginPredicate(const PluginPredicate &)` | Deleted. The class is not copyable. | This page |

## Initialization
```cpp
explicit PluginPredicate(const std::string &so_path);
```
The constructor opens the library with `RTLD_NOW | RTLD_LOCAL`. The library must export `ax_create_predicate` and `ax_destroy_predicate`. The constructor calls `ax_create_predicate` with a null argument. The plugin must be built against the same `Frame` layout.

| Exception | Trigger |
|---|---|
| `std::runtime_error` | `dlopen` fails. |
| `std::runtime_error` | A required symbol is missing. |
| `std::runtime_error` | `ax_create_predicate` returns null. |

## Lifecycle
The destructor calls `ax_destroy_predicate` on the created predicate. It then calls `dlclose`.

## Related Classes
| Class | Relationship |
|---|---|
| [Predicate](Predicate.md) | Base class and the type the plugin creates. |
| [PipelineBuilder](PipelineBuilder.md) | Constructs it from the spec. |

## Source Reference
`server/include/pipeline/predicate.h::Ax::PluginPredicate` (lines 105-156)
