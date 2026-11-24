#!/usr/bin/env python3

"""Release test for the three-stage cascade example: launch it through the helper CLI and check detections, keypoints and faces on a test image.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from utils import examples_run as ex

NAME = 'test_release_examples_cascade3'
MODELS = ['yolox-m-coco-onnx', 'yolo26npose-coco-onnx', 'retinaface-mobilenet0.25-widerface-onnx']
IMAGE = ex.ASSETS / 'dancing_frame_t15_480p.jpg'
STREAMS, FRAMES = 2, 100


def body() -> None:
    """Run the three-stage cascade scenario (yolox-m, yolo26npose, retinaface) and tear the pipeline down afterwards.

    Raises:
        StepFailed: If the environment is incomplete, the test image is missing, a helper command fails, or the demo reports no detections, keypoints or faces.
    """
    ex.require_env()
    if not IMAGE.is_file():
        raise ex.StepFailed(f'{IMAGE} is missing')
    compiled = None
    with tempfile.TemporaryDirectory(prefix='examples_cascade3_') as tmp:
        try:
            compiled, endpoints = ex.launch_vision('cascade3', ['--secondary-meta-key-override'], MODELS, Path(tmp))
            stats = ex.demo(endpoints, IMAGE, STREAMS, FRAMES)
            ex.require_positive(stats, 'detections', 'keypoints', 'faces')
        finally:
            if compiled is not None:
                ex.helper('down', str(compiled), what='helper down')


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
