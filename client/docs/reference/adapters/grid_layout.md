# grid_layout

## Summary

Chooses the number of columns and rows for a tile grid.

## Detailed Description

### Behavior

Without `grid`, the function computes `cols = ceil(sqrt(count))` and `rows = ceil(count / cols)`. With `grid`, it parses `COLSxROWS` and checks that the grid holds at least `count` tiles.

### Concurrency

This function is stateless. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def grid_layout(count: int, grid: Optional[str] = None) -> tuple[int, int]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| count | int | none | yes | Number of tiles to place. |
| grid | Optional[str] | `None` | no | Explicit `COLSxROWS`. If `None`, a near-square grid is computed. |

## Returns

`tuple[int, int]`. The pair `(cols, rows)`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| ValueError | `count < 1`, `grid` is malformed, or `grid` has fewer cells than `count`. | Pass a larger grid or fewer tiles. |

## Usage Examples

### Basic

```python
from adapters.common.rendering import grid_layout

cols, rows = grid_layout(5)  # (3, 2)
```

## Edge Cases

- `grid` is case-insensitive (`'3X2'` works).
- The auto grid can have empty cells, for example 5 tiles give 3x2.

## Related APIs

| API | Relationship |
|---|---|
| [cell_rects](cell_rects.md) | Turns the grid into pixel rectangles. |
| [parse_canvas_size](parse_canvas_size.md) | Provides the canvas size. |

## Source Reference

- `client/adapters/common/rendering.py::grid_layout` (lines 391-416)
