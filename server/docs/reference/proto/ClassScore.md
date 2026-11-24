# ClassScore

## Overview

`ClassScore` is a class prediction with its score. `Detection.classifications` and `FrameResult.classifications` hold it.

## Fields

| Field | Number | Type | Label | Description |
|---|---|---|---|---|
| `class_id` | 1 | `uint32` | singular | Class index. |
| `label` | 2 | `string` | singular | Class name. |
| `score` | 3 | `float` | singular | Score of the class. |

## Related Messages

- [Detection](Detection.md)
- [FrameResult](FrameResult.md)

## Source Reference

- `proto/axinfer/v1/inference.proto::ClassScore` (lines 24-28)
