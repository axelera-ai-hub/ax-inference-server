# MetaKeyExistsPredicate

## Overview
`Ax::MetaKeyExistsPredicate` is a [Predicate](Predicate.md) that is true when `Frame::meta` contains a given key. The JSON spec uses `type: "meta_key_exists"`.

## Attributes
This class has no public attributes. The constructor takes the key to look for in `Frame::meta`.

## Methods
| Method | Summary | Page |
|---|---|---|
| `eval(const Frame &frame) const` | Returns true when `Frame::meta` contains the configured `meta_key`. | [Predicate](Predicate.md) |

## Initialization
```cpp
explicit MetaKeyExistsPredicate(std::string meta_key);
```
The JSON predicate needs one field, `meta_key`.

## Lifecycle
The object holds only the key. It has no resources to release.

## Related Classes
| Class | Relationship |
|---|---|
| [Predicate](Predicate.md) | Base class. |
| [KptsConfidencePredicate](KptsConfidencePredicate.md) | Sibling built-in predicate. |

## Source Reference
`server/include/pipeline/predicate.h::Ax::MetaKeyExistsPredicate` (lines 34-46), `server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502)
