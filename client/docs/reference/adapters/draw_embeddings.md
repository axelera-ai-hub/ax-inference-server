# draw_embeddings

## Summary

Annotates embedding summaries below each detection.

## Detailed Description

### Behavior

Each summary line reads `key[dim] |v|=norm`, where `norm` is the L2 norm of the vector. Embeddings with key `reid` go below the person box. Other embeddings go below the face box when `face_bbox` is set. Otherwise they continue below the `reid` lines. Lines are 16 pixels apart and use BGR `(0, 255, 255)`.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_embeddings(raw: np.ndarray, detections) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| detections | iterable of detection messages | none | yes | Messages with `bbox`, optional `face_bbox` and an `embeddings` list. Each embedding has `key` and `vector`. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_embeddings

draw_embeddings(frame.raw, response.detections)
```

## Edge Cases

- Embeddings with an empty vector are skipped.
- A detection without usable embeddings is skipped.

## Related APIs

| API | Relationship |
|---|---|
| [draw_detections](draw_detections.md) | Sibling overlay for boxes. |
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_embeddings` (lines 206-233)
