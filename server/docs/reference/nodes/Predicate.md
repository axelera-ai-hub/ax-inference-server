# Predicate

## Overview
`Ax::Predicate` is the abstract boolean test on a frame. `ConditionNode` and `LoopGuardNode` use predicates to decide routing. `PipelineBuilder` creates predicates from the `predicates` object of the JSON spec.

## Attributes
The class has no data members.

## Methods
| Method | Summary | Page |
|---|---|---|
| `eval(const Frame &frame) const` | Pure virtual. Returns the result of the test as `bool`. | This page |
| `~Predicate()` | Virtual default destructor. | This page |

## Initialization
A derived class implements `eval()`. The builder constructs these classes.

| JSON `type` | Class | Fields |
|---|---|---|
| `meta_key_exists` | [MetaKeyExistsPredicate](MetaKeyExistsPredicate.md) | `meta_key` |
| `kpts_conf_gt` | [KptsConfidencePredicate](KptsConfidencePredicate.md) | `meta_key`, `indices`, `value` |
| `plugin` | [PluginPredicate](PluginPredicate.md) | `so_path` |

The builder throws `std::runtime_error` for any other type.

## Lifecycle
The builder stores each predicate in a `std::shared_ptr<Predicate>`. Nodes call `eval()` for each frame. `eval()` is const. Concurrency behavior depends on the underlying runtime.

## Related Classes
| Class | Relationship |
|---|---|
| [ConditionNode](ConditionNode.md) | Routes on `eval()`. |
| [LoopGuardNode](LoopGuardNode.md) | Ends a loop when `eval()` is true. |
| [Frame](Frame.md) | Argument of `eval()`. |

Concept page: [vision/pipeline.md](../../vision/pipeline.md).

## Source Reference
`server/include/pipeline/predicate.h::Ax::Predicate` (lines 18-31)
