# parse_canvas_size

## Summary

Resolves a canvas size preset or `WxH` string to width and height.

## Detailed Description

### Behavior

The function strips and lowercases `spec`. It looks the result up in the module constant `CANVAS_SIZES`. Otherwise it parses `WxH`. Presets: 360p (640x360), 480p (854x480), 720p (1280x720), 1080p (1920x1080), 1440p (2560x1440), 2160p (3840x2160).

### Concurrency

This function is stateless. Concurrency behavior depends on the underlying runtime.

### Constraints

None beyond the parameter types.

## Signature

```python
def parse_canvas_size(spec: str) -> tuple[int, int]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| spec | str | none | yes | A key of `CANVAS_SIZES` such as `'720p'`, or `WxH` such as `'1280x720'`. |

## Returns

`tuple[int, int]`. Width and height in pixels.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| ValueError | `spec` is neither a preset nor `WxH`, or a side is below 2. | Pass a preset or two integers joined by `x`. |

## Usage Examples

### Basic

```python
from adapters.common.rendering import parse_canvas_size

w, h = parse_canvas_size('720p')  # (1280, 720)
```

## Edge Cases

- Input is case-insensitive and surrounding whitespace is ignored.
- `'1280x720x1'` raises `ValueError`.

## Related APIs

| API | Relationship |
|---|---|
| [grid_layout](grid_layout.md) | Chooses the tile grid for the canvas. |
| [cell_rects](cell_rects.md) | Splits the canvas into cells. |

## Source Reference

- `client/adapters/common/rendering.py::parse_canvas_size` (lines 367-388)
- `client/adapters/common/rendering.py::CANVAS_SIZES` (lines 363-364)
