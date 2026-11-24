"""Drawing, encoding and layout helpers for rendering annotated frames.

Covers detection, track, keypoint, segmentation, face and embedding overlays, frame
resize/encode/save utilities, a bounded on-disk frame ring, and tiled-canvas layout helpers.

Note:
    The ring-buffer state is module-global and protected by a lock; the drawing helpers modify frames in place.
"""
from __future__ import annotations

import collections
import os
import threading
from typing import Optional

import cv2
import numpy as np

_RING_BUFFER_STATE: dict = {}
_RING_BUFFER_LOCK = threading.Lock()


def draw_detections(raw: np.ndarray, detections) -> None:
    """Draw green bounding boxes with 'label score' captions onto a frame, in place.

    Detections whose box has zero width or height are skipped.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        detections: Iterable of detection messages with bbox (x, y, w, h), label and score.
    """
    for det in detections:
        box = det.bbox
        if box.w == 0 or box.h == 0:
            continue
        x1, y1 = int(box.x), int(box.y)
        x2, y2 = x1 + int(box.w), y1 + int(box.h)
        cv2.rectangle(raw, (x1, y1), (x2, y2), (0, 255, 0), 2)
        text = f'{det.label} {det.score:.2f}'
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_y0 = max(0, y1 - th - 6)
        cv2.rectangle(raw, (x1, label_y0), (x1 + tw + 4, y1), (0, 255, 0), -1)
        cv2.putText(raw, text, (x1 + 2, max(th, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1, cv2.LINE_AA)


def draw_tracks(raw: np.ndarray, tracked) -> None:
    """Draw tracked-object boxes with '#id label' captions onto a frame, in place.

    Each track id maps to a fixed colour; tracks with a negative id are skipped.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        tracked: Iterable of tracked objects with track_id, label and x, y, w, h.
    """
    for td in tracked:
        if td.track_id < 0:
            continue
        color = ((td.track_id * 67) % 200 + 55, (td.track_id * 131) % 200 + 55, (td.track_id * 29) % 200 + 55)
        x1, y1, x2, y2 = int(td.x), int(td.y), int(td.x + td.w), int(td.y + td.h)
        cv2.rectangle(raw, (x1, y1), (x2, y2), color, 2)
        text = f'#{td.track_id} {td.label}'
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_y0 = max(0, y1 - th - 6)
        cv2.rectangle(raw, (x1, label_y0), (x1 + tw + 4, y1), color, -1)
        cv2.putText(raw, text, (x1 + 2, max(th, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)


SKELETON_BOUNDS = (
    (15, 13, 11, 5, 6, 12, 14, 16),
    (5, 7, 9),
    (6, 8, 10),
)
_KEYPOINT_LINE_MIN_CONFIDENCE = 0.5
_KEYPOINT_POINT_MIN_CONFIDENCE = 0.3
_KEYPOINT_COLOR = (0, 165, 255)


def _keypoint_confidence(point) -> float:
    """Return a keypoint's confidence, or 0.0 when the field is unset."""
    return point.confidence if point.HasField('confidence') else 0.0


def _draw_skeleton(raw: np.ndarray, points: list, color: tuple) -> None:
    """Draw the limb and torso lines of a 17-point COCO skeleton.

    Only segments between keypoints above the line confidence threshold are drawn.
    Does nothing when fewer than 17 points are given. A line from the nose (0) to the
    midpoint of the shoulders (5, 6) is added when all three are visible.
    """
    if len(points) < 17:
        return

    def pt(i):
        return (int(points[i].x), int(points[i].y))

    def visible(i):
        return _keypoint_confidence(points[i]) > _KEYPOINT_LINE_MIN_CONFIDENCE

    for bound in SKELETON_BOUNDS:
        line = [pt(i) for i in bound if visible(i)]
        for a, b in zip(line, line[1:]):
            cv2.line(raw, a, b, color, 2, cv2.LINE_AA)

    if visible(0) and visible(5) and visible(6):
        p5, p6 = pt(5), pt(6)
        mid = (int((p5[0] + p6[0]) / 2), int((p5[1] + p6[1]) / 2))
        cv2.line(raw, pt(0), mid, color, 2, cv2.LINE_AA)


def draw_keypoints(raw: np.ndarray, detections) -> None:
    """Draw pose skeletons and keypoint dots for each detection, in place.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        detections: Iterable of detection messages with a keypoints list.
    """
    for det in detections:
        points = list(det.keypoints)
        if not points:
            continue
        _draw_skeleton(raw, points, _KEYPOINT_COLOR)
        for point in points:
            if _keypoint_confidence(point) < _KEYPOINT_POINT_MIN_CONFIDENCE:
                continue
            cv2.circle(raw, (int(point.x), int(point.y)), 3, _KEYPOINT_COLOR, -1, cv2.LINE_AA)


_SEGMENTATION_COLOR = (255, 0, 255)
_SEGMENTATION_ALPHA = 125 / 255


def draw_segmentation(raw: np.ndarray, detections) -> None:
    """Draw translucent filled segmentation polygons with outlines, in place.

    Polygons with fewer than 3 points are skipped. All polygons share one blended overlay.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        detections: Iterable of detection messages with a segmentation point list.
    """
    polygons = []
    for det in detections:
        points = list(det.segmentation)
        if len(points) < 3:
            continue
        polygons.append(np.array([[int(p.x), int(p.y)] for p in points], dtype=np.int32))
    if not polygons:
        return

    overlay = raw.copy()
    for poly in polygons:
        cv2.fillPoly(overlay, [poly], _SEGMENTATION_COLOR)
    cv2.addWeighted(overlay, _SEGMENTATION_ALPHA, raw, 1 - _SEGMENTATION_ALPHA, 0, dst=raw)
    for poly in polygons:
        cv2.polylines(raw, [poly], True, _SEGMENTATION_COLOR, 2, cv2.LINE_AA)


_FACE_COLOR = (255, 255, 0)
_FACE_LANDMARK_RADIUS = 2


def draw_face(raw: np.ndarray, detections) -> None:
    """Draw face boxes (captioned 'face') and landmark dots, in place.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        detections: Iterable of detection messages with optional face_bbox and face_landmarks.
    """
    for det in detections:
        has_face_bbox = det.HasField('face_bbox')
        landmarks = list(det.face_landmarks)
        if not has_face_bbox and not landmarks:
            continue
        if has_face_bbox:
            box = det.face_bbox
            x1, y1 = int(box.x), int(box.y)
            x2, y2 = x1 + int(box.w), y1 + int(box.h)
            cv2.rectangle(raw, (x1, y1), (x2, y2), _FACE_COLOR, 2)
            (tw, th), _ = cv2.getTextSize('face', cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.putText(raw, 'face', (x1, y2 + th + 4), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, _FACE_COLOR, 1, cv2.LINE_AA)
        for point in landmarks:
            cv2.circle(raw, (int(point.x), int(point.y)), _FACE_LANDMARK_RADIUS, _FACE_COLOR, -1, cv2.LINE_AA)


_EMBEDDING_COLOR = (0, 255, 255)
_EMBEDDING_LINE_HEIGHT = 16


def _draw_embedding_lines(raw: np.ndarray, embeddings: list, x: int, y: int) -> int:
    """Draw one 'key[dim] |v|=norm' text line per embedding, stacked downwards.

    Returns:
        int: The y coordinate for the next line.
    """
    for emb in embeddings:
        vector = emb.vector
        norm = sum(v * v for v in vector) ** 0.5
        text = f'{emb.key}[{len(vector)}] |v|={norm:.2f}'
        cv2.putText(raw, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _EMBEDDING_COLOR, 1, cv2.LINE_AA)
        y += _EMBEDDING_LINE_HEIGHT
    return y


def draw_embeddings(raw: np.ndarray, detections) -> None:
    """Annotate embedding summaries (key, dimension, L2 norm) below each detection.

    'reid' embeddings go under the person box; other embeddings go under the face box when
    one exists, otherwise below the reid lines. Embeddings with an empty vector are skipped.

    Args:
        raw (np.ndarray): BGR frame, modified in place.
        detections: Iterable of detection messages with bbox, optional face_bbox and embeddings.
    """
    for det in detections:
        embeddings = [e for e in det.embeddings if len(e.vector) > 0]
        if not embeddings:
            continue
        reid_embeddings = [e for e in embeddings if e.key == 'reid']
        other_embeddings = [e for e in embeddings if e.key != 'reid']

        box = det.bbox
        person_x, person_y = int(box.x), int(box.y) + int(box.h) + 2
        person_y = _draw_embedding_lines(raw, reid_embeddings, person_x, person_y)

        if det.HasField('face_bbox'):
            face_box = det.face_bbox
            other_x = int(face_box.x)
            other_y = int(face_box.y) + int(face_box.h) + 16
        else:
            other_x, other_y = person_x, person_y
        _draw_embedding_lines(raw, other_embeddings, other_x, other_y)


def resize_frame(raw: np.ndarray, max_width_px: int) -> np.ndarray:
    """Downscale a frame to at most a given width, keeping the aspect ratio.

    Args:
        raw (np.ndarray): BGR frame.
        max_width_px (int): Maximum width in pixels. Values <= 0 disable resizing.

    Returns:
        np.ndarray: The original frame if no resize is needed, otherwise a resized copy.
    """
    if max_width_px <= 0:
        return raw
    h, w = raw.shape[:2]
    if w <= max_width_px:
        return raw
    scale = max_width_px / w
    new_size = (max_width_px, max(1, round(h * scale)))
    return cv2.resize(raw, new_size, interpolation=cv2.INTER_AREA)


def decode_frame(data: bytes) -> Optional[np.ndarray]:
    """Decode encoded image bytes to a BGR array; returns None if decoding fails."""
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def resize_to_height(raw: np.ndarray, target_height_px: int) -> np.ndarray:
    """Downscale a frame to at most a given height, keeping the aspect ratio.

    Args:
        raw (np.ndarray): BGR frame.
        target_height_px (int): Maximum height in pixels. Values <= 0 disable resizing.

    Returns:
        np.ndarray: The original frame if no resize is needed, otherwise a resized copy.
    """
    if target_height_px <= 0:
        return raw
    h, w = raw.shape[:2]
    if h <= target_height_px:
        return raw
    scale = target_height_px / h
    new_size = (max(1, round(w * scale)), target_height_px)
    return cv2.resize(raw, new_size, interpolation=cv2.INTER_AREA)


def encode_frame(raw: np.ndarray, fmt: str, quality: int) -> bytes:
    """Encode a frame as WebP or JPEG.

    Args:
        raw (np.ndarray): BGR frame.
        fmt (str): 'webp' for WebP; any other value selects JPEG.
        quality (int): Encoder quality passed to OpenCV.

    Returns:
        bytes: The encoded image.

    Raises:
        RuntimeError: If cv2.imencode fails.
    """
    ext = '.webp' if fmt == 'webp' else '.jpg'
    param = cv2.IMWRITE_WEBP_QUALITY if fmt == 'webp' else cv2.IMWRITE_JPEG_QUALITY
    ok, buf = cv2.imencode(ext, raw, [param, quality])
    if not ok:
        raise RuntimeError(f"cv2.imencode failed for format {fmt!r}")
    return buf.tobytes()


def save_frame(directory: str, filename: str, raw: np.ndarray) -> str:
    """Write a frame to disk atomically.

    The image is written to a '.tmp' subdirectory first and then renamed into place, so
    readers never see a partial file.

    Args:
        directory (str): Destination directory; created if missing.
        filename (str): File name; the extension selects the image format.
        raw (np.ndarray): BGR frame.

    Returns:
        str: Path of the saved file.

    Raises:
        RuntimeError: If cv2.imwrite fails.
    """
    os.makedirs(directory, exist_ok=True)
    tmp_dir = os.path.join(directory, '.tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(directory, filename)
    tmp_path = os.path.join(tmp_dir, filename)
    ok = cv2.imwrite(tmp_path, raw)
    if not ok:
        raise RuntimeError(f"cv2.imwrite failed: {tmp_path}")
    os.rename(tmp_path, path)
    return path


def evict_oldest(directory: str, filename: str, keep_last_n: int) -> None:
    """Record a saved file and delete the oldest ones beyond a retention limit.

    Keeps a per-directory FIFO of file names in module state, guarded by a lock. Files that
    are already gone are ignored.

    Args:
        directory (str): Directory the file was saved in.
        filename (str): Name of the newly saved file.
        keep_last_n (int): Number of most recent files to keep in this directory.
    """
    to_remove = []
    with _RING_BUFFER_LOCK:
        names = _RING_BUFFER_STATE.setdefault(directory, collections.deque())
        names.append(filename)
        excess = len(names) - keep_last_n
        for _ in range(max(0, excess)):
            to_remove.append(names.popleft())
    for name in to_remove:
        try:
            os.remove(os.path.join(directory, name))
        except FileNotFoundError:
            pass


def reset_ring_buffer(directory: str) -> None:
    """Forget the tracked file names for a directory without deleting any files."""
    with _RING_BUFFER_LOCK:
        _RING_BUFFER_STATE.pop(directory, None)


CANVAS_SIZES = {'360p': (640, 360), '480p': (854, 480), '720p': (1280, 720), '1080p': (1920, 1080),
                '1440p': (2560, 1440), '2160p': (3840, 2160)}


def parse_canvas_size(spec: str) -> tuple[int, int]:
    """Resolve a canvas size preset or 'WxH' string to (width, height) in pixels.

    Args:
        spec (str): A key of CANVAS_SIZES such as '720p', or 'WxH' such as '1280x720'.

    Returns:
        tuple[int, int]: Width and height.

    Raises:
        ValueError: If spec is neither a preset nor WxH, or a side is below 2.
    """
    spec = spec.strip().lower()
    if spec in CANVAS_SIZES:
        return CANVAS_SIZES[spec]
    try:
        w, h = (int(v) for v in spec.split('x'))
    except ValueError:
        raise ValueError(f'canvas size must be one of {", ".join(CANVAS_SIZES)} or WxH, got {spec!r}') from None
    if w < 2 or h < 2:
        raise ValueError(f'canvas size must be at least 2x2, got {spec!r}')
    return w, h


def grid_layout(count: int, grid: Optional[str] = None) -> tuple[int, int]:
    """Choose the number of columns and rows for a tile grid.

    Args:
        count (int): Number of tiles to place.
        grid (Optional[str], optional): Explicit 'COLSxROWS'. If None, a near-square grid is
            computed. Defaults to None.

    Returns:
        tuple[int, int]: (cols, rows).

    Raises:
        ValueError: If count < 1, grid is malformed, or grid has fewer cells than count.
    """
    if count < 1:
        raise ValueError('need at least one tile')
    if grid is None:
        cols = int(np.ceil(np.sqrt(count)))
        return cols, int(np.ceil(count / cols))
    try:
        cols, rows = (int(v) for v in grid.lower().split('x'))
    except ValueError:
        raise ValueError(f'grid must be COLSxROWS, got {grid!r}') from None
    if cols < 1 or rows < 1 or cols * rows < count:
        raise ValueError(f'grid {grid} holds {max(cols, 0) * max(rows, 0)} tiles, {count} needed')
    return cols, rows


def cell_rects(canvas_w: int, canvas_h: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    """Split a canvas into a cols x rows grid of rectangles.

    Cell edges use integer division so the cells tile the canvas exactly.

    Returns:
        list[tuple[int, int, int, int]]: (x, y, w, h) per cell, row-major order.
    """
    xs = [canvas_w * c // cols for c in range(cols + 1)]
    ys = [canvas_h * r // rows for r in range(rows + 1)]
    return [(xs[c], ys[r], xs[c + 1] - xs[c], ys[r + 1] - ys[r]) for r in range(rows) for c in range(cols)]


def letterbox(raw: np.ndarray, width: int, height: int) -> np.ndarray:
    """Fit a frame inside a width x height black canvas, centred, keeping the aspect ratio.

    Returns:
        np.ndarray: A new (height, width, 3) uint8 image.
    """
    h, w = raw.shape[:2]
    scale = min(width / w, height / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    out = np.zeros((height, width, 3), np.uint8)
    x, y = (width - nw) // 2, (height - nh) // 2
    out[y:y + nh, x:x + nw] = cv2.resize(raw, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    return out


def put_label(canvas: np.ndarray, text: str, x: int, y: int, scale: float = 0.6, anchor: str = 'top-left') -> None:
    """Draw white text on a black background box, in place.

    Args:
        canvas (np.ndarray): BGR image, modified in place.
        text (str): Label text.
        x (int): Left edge of the box.
        y (int): Top edge of the box, or its bottom edge when anchor is 'bottom-left'.
        scale (float, optional): Font scale. Defaults to 0.6.
        anchor (str, optional): 'top-left' or 'bottom-left'. Defaults to 'top-left'.
    """
    thick = max(1, round(scale * 2))
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    pad = max(2, th // 3)
    if anchor == 'bottom-left':
        y -= th + base + 2 * pad
    cv2.rectangle(canvas, (x, y), (x + tw + 2 * pad, y + th + base + 2 * pad), (0, 0, 0), -1)
    cv2.putText(canvas, text, (x + pad, y + th + pad), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA)


def load_logo(path: str, width: int) -> Optional[np.ndarray]:
    """Load an image with an alpha channel and scale it to a given width.

    Returns:
        Optional[np.ndarray]: BGRA image, or None if the file cannot be read or has no alpha channel.
    """
    logo = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if logo is None or logo.ndim != 3 or logo.shape[2] != 4:
        return None
    height = max(1, round(logo.shape[0] * width / logo.shape[1]))
    return cv2.resize(logo, (max(1, width), height), interpolation=cv2.INTER_AREA)


def overlay_logo(canvas: np.ndarray, logo: np.ndarray, margin: int, opacity: float = 0.85) -> None:
    """Alpha-blend a BGRA logo into the bottom-right corner of a canvas, in place.

    Does nothing if the logo plus margin does not fit.

    Args:
        canvas (np.ndarray): BGR image, modified in place.
        logo (np.ndarray): BGRA image from load_logo.
        margin (int): Distance in pixels from the right and bottom edges.
        opacity (float, optional): Extra multiplier on the logo's alpha. Defaults to 0.85.
    """
    lh, lw = logo.shape[:2]
    ch, cw = canvas.shape[:2]
    x, y = cw - lw - margin, ch - lh - margin
    if x < 0 or y < 0:
        return
    alpha = (logo[:, :, 3:4].astype(np.float32) / 255.0) * opacity
    roi = canvas[y:y + lh, x:x + lw]
    roi[:] = (logo[:, :, :3] * alpha + roi * (1.0 - alpha)).astype(np.uint8)
