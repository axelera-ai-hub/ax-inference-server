#!/usr/bin/env python3

"""Release test for the single-model vision example: launch isovision with yolox-m, check throughput, and render an annotated canvas video.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from utils import examples_run as ex
from utils import release_gate

NAME = 'test_release_examples_vision'
MODEL = 'yolox-m-coco-onnx'
VIDEO = ex.ASSETS / 'intersection_480p.mp4'
STREAMS, FRAMES = 4, 1500
# Soft throughput floor (fps, median); a miss logs a warning and does not fail the test.
MIN_FPS = 320
CANVAS_STREAMS, CANVAS_FRAMES = 2, 60
# Smallest canvas video size (bytes) accepted as a real recording.
MIN_MP4_BYTES = 10_000


def body() -> None:
    """Run the vision scenario: fetch media, launch one pipeline, run the demo, then render a canvas video.

    Raises:
        StepFailed: If the environment is incomplete, the video is missing, the demo reports no detections, the canvas output is not reported, or the written mp4 is missing or too small.
    """
    ex.require_env()
    ex.helper('media')
    if not VIDEO.is_file():
        raise ex.StepFailed(f'{VIDEO} is missing after helper media')
    compiled = None
    with tempfile.TemporaryDirectory(prefix='examples_vision_') as tmp:
        work = Path(tmp)
        try:
            compiled, endpoints = ex.launch_vision('isovision', ['--model', MODEL], [MODEL], work)
            stats = ex.demo(endpoints, VIDEO, STREAMS, FRAMES)
            ex.require_positive(stats, 'detections')
            if stats['fps_p50'] < MIN_FPS:
                release_gate.warn(f'throughput {stats["fps_p50"]:.1f} fps is below the {MIN_FPS} fps floor ({MODEL}, one device, four cores)')
            mp4 = work / 'canvas.mp4'
            res = ex.example('vision_demo.py', '--endpoints', ','.join(endpoints), '--source', str(VIDEO),
                             '--streams', str(CANVAS_STREAMS), '--frames', str(CANVAS_FRAMES), '--canvas', '480p', '--output', str(mp4))
            if 'annotated canvas:' not in res.stdout:
                raise ex.StepFailed('vision_demo.py did not report the annotated canvas')
            if not mp4.is_file() or mp4.stat().st_size < MIN_MP4_BYTES:
                raise ex.StepFailed(f'canvas video {mp4} is missing or smaller than {MIN_MP4_BYTES} bytes')
            ex.passed(f'canvas video written ({mp4.stat().st_size} bytes)')
        finally:
            if compiled is not None:
                ex.helper('down', str(compiled), what='helper down')


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
