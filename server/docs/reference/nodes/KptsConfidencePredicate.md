# KptsConfidencePredicate

## Overview
`Ax::KptsConfidencePredicate` is a [Predicate](Predicate.md) that is true when selected keypoints of the first detection all exceed a visibility threshold. The JSON spec uses `type: "kpts_conf_gt"`.

## Attributes
This class has no public attributes. The constructor takes the keypoint meta key, the keypoint indices that must pass and `min_confidence`, an exclusive lower bound on each keypoint's visibility.

## Methods
| Method | Summary | Page |
|---|---|---|
| `eval(const Frame &frame) const` | Returns true when every selected keypoint of detection 0 has visibility above the threshold. | [Predicate](Predicate.md) |

`eval()` returns false in these cases:

- The meta key is missing.
- The meta is not an `AxMetaKptsDetection`.
- The keypoint count is 0.
- An index is negative or out of range.
- Any selected keypoint has visibility less than or equal to the threshold.
- Reading the keypoints throws `std::out_of_range`.

The keypoint count is 17 when the keypoint shape is empty.

## Initialization
```cpp
KptsConfidencePredicate(std::string meta_key, std::vector<int> indices, float min_confidence);
```

| JSON field | Maps to |
|---|---|
| `meta_key` | `meta_key` |
| `indices` | `indices` |
| `value` | `min_confidence` |

## Lifecycle
The object holds only configuration. It has no resources to release.

## Related Classes
| Class | Relationship |
|---|---|
| [Predicate](Predicate.md) | Base class. |
| [MetaKeyExistsPredicate](MetaKeyExistsPredicate.md) | Sibling built-in predicate. |

## Source Reference
`server/include/pipeline/predicate.h::Ax::KptsConfidencePredicate` (lines 56-94), `server/src/pipeline/builder.cpp::PipelineBuilder::build` (lines 189-502)
