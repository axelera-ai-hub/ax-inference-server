# draw_keypoints

## Summary

Draws pose skeletons and keypoint dots for each detection.

## Detailed Description

### Behavior

For each detection with keypoints, the function draws the skeleton lines described by `SKELETON_BOUNDS`. It then draws an orange dot (BGR `(0, 165, 255)`) for each keypoint with confidence of at least 0.3. Each `SKELETON_BOUNDS` segment keeps only its visible points (confidence above 0.5). The function draws a line between each pair of consecutive visible points. It skips a hidden joint. The skeleton needs 17 points (COCO layout). A line from the nose (index 0) to the midpoint of the shoulders (5 and 6) is added when all three are visible. A keypoint without a `confidence` field counts as 0.0.

### Concurrency

This function modifies the frame in place and has no locking. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def draw_keypoints(raw: np.ndarray, detections) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| raw | np.ndarray | none | yes | BGR frame, modified in place. |
| detections | iterable of detection messages | none | yes | Messages with a `keypoints` list. Each point has `x`, `y` and optional `confidence`. |

## Returns

`None`. The function draws onto `raw`.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import draw_keypoints

draw_keypoints(frame.raw, response.detections)
```

## Edge Cases

- A detection with an empty `keypoints` list is skipped.
- With fewer than 17 points the function draws dots but no skeleton lines.
- `SKELETON_BOUNDS` is a module constant of three index tuples: legs and torso, left arm, right arm.

## Related APIs

| API | Relationship |
|---|---|
| [draw_detections](draw_detections.md) | Sibling overlay for boxes. |
| [index](index.md) | All adapter and rendering pages. |

## Source Reference

- `client/adapters/common/rendering.py::draw_keypoints` (lines 111-126)
- `client/adapters/common/rendering.py::SKELETON_BOUNDS` (lines 69-73)
