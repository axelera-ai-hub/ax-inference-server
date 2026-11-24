# cell_rects

## Summary

Splits a canvas into a grid of rectangles.

## Detailed Description

### Behavior

Cell edges use integer division, so the cells tile the canvas exactly with no gaps. The function returns the cells in row-major order.

### Concurrency

This function is stateless. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def cell_rects(canvas_w: int, canvas_h: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| canvas_w | int | none | yes | Canvas width in pixels. |
| canvas_h | int | none | yes | Canvas height in pixels. |
| cols | int | none | yes | Number of columns. |
| rows | int | none | yes | Number of rows. |

## Returns

`list[tuple[int, int, int, int]]`. One `(x, y, w, h)` per cell, row-major.

## Exceptions

None raised by this code.

## Usage Examples

### Basic

```python
from adapters.common.rendering import cell_rects

rects = cell_rects(1280, 720, 2, 2)  # 4 cells of 640x360
```

## Edge Cases

- The function does not validate `cols` or `rows`. A value of 0 raises `ZeroDivisionError`.
- Cell sizes differ by at most one pixel.

## Related APIs

| API | Relationship |
|---|---|
| [grid_layout](grid_layout.md) | Supplies `cols` and `rows`. |
| [letterbox](letterbox.md) | Fits a frame into one cell. |

## Source Reference

- `client/adapters/common/rendering.py::cell_rects` (lines 419-429)
