# Adapters reference

## Overview

The `client/adapters` package turns video files, still images and webcams into `Frame` objects for the inference client. `adapters.common.rendering` adds helpers that draw results, encode and save frames, and lay out tiled canvases. The concept page is [adapters](../../client/adapters.md).

## Architecture

```mermaid
flowchart LR
    S[SourceAdapter subclass] --> F[Frame]
    F --> C[Inference client]
    C --> R[draw_* helpers]
    R --> E[encode_frame / save_frame]
```

The package root re-exports `Frame`, `SourceAdapter`, `SourceAdapterError`, `VideoFileAdapterCV`, `ImageAdapterCV`, `WebcamAdapterCV` and `WebcamDeviceInfo`. The rendering functions live in `adapters.common.rendering`. That module also defines the constants `SKELETON_BOUNDS` and `CANVAS_SIZES`.

## Pages

| Page | Kind | Summary |
|---|---|---|
| [SourceAdapter](SourceAdapter.md) | class | Abstract base class for frame sources. |
| [SourceAdapter.read_frame](SourceAdapter.read_frame.md) | function | Reads and numbers the next frame. |
| [Frame](Frame.md) | class | Dataclass for one captured frame. |
| [SourceAdapterError](SourceAdapterError.md) | class | Error raised by adapters. |
| [VideoFileAdapterCV](VideoFileAdapterCV.md) | class | Reads frames from a video file. |
| [ImageAdapterCV](ImageAdapterCV.md) | class | Serves one still image repeatedly. |
| [WebcamAdapterCV](WebcamAdapterCV.md) | class | Reads live frames from a camera. |
| [WebcamAdapterCV.list_devices](WebcamAdapterCV.list_devices.md) | function | Lists `/dev/video*` capture devices. |
| [WebcamDeviceInfo](WebcamDeviceInfo.md) | class | Describes one V4L2 capture device. |
| [draw_detections](draw_detections.md) | function | Draws boxes with label and score. |
| [draw_tracks](draw_tracks.md) | function | Draws tracked boxes with ids. |
| [draw_keypoints](draw_keypoints.md) | function | Draws pose skeletons and keypoints. |
| [draw_segmentation](draw_segmentation.md) | function | Draws translucent segmentation polygons. |
| [draw_face](draw_face.md) | function | Draws face boxes and landmarks. |
| [draw_embeddings](draw_embeddings.md) | function | Annotates embedding key, size and norm. |
| [resize_frame](resize_frame.md) | function | Downscales a frame to a maximum width. |
| [resize_to_height](resize_to_height.md) | function | Downscales a frame to a maximum height. |
| [decode_frame](decode_frame.md) | function | Decodes image bytes to a BGR array. |
| [encode_frame](encode_frame.md) | function | Encodes a frame as WebP or JPEG. |
| [save_frame](save_frame.md) | function | Writes a frame to disk atomically. |
| [evict_oldest](evict_oldest.md) | function | Deletes the oldest saved files beyond a limit. |
| [reset_ring_buffer](reset_ring_buffer.md) | function | Forgets tracked file names for a directory. |
| [parse_canvas_size](parse_canvas_size.md) | function | Resolves a preset or `WxH` to a size. |
| [grid_layout](grid_layout.md) | function | Chooses columns and rows for tiles. |
| [cell_rects](cell_rects.md) | function | Splits a canvas into cell rectangles. |
| [letterbox](letterbox.md) | function | Fits a frame into a black canvas. |
| [put_label](put_label.md) | function | Draws a text label on a black box. |
| [load_logo](load_logo.md) | function | Loads a BGRA logo scaled to a width. |
| [overlay_logo](overlay_logo.md) | function | Blends a logo into the bottom-right corner. |

## Quick Example

```python
from adapters import VideoFileAdapterCV
from adapters.common.rendering import resize_frame, encode_frame

with VideoFileAdapterCV('clip.mp4', loop=False) as src:
    frame = src.read_frame()
    if frame is not None:
        small = resize_frame(frame.raw, 640)
        data = encode_frame(small, 'webp', 80)
```
