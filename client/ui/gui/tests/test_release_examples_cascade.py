#!/usr/bin/env python3

"""Release test for the two-stage cascade example: launch it through the helper CLI and check detections and keypoints on a test image.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from utils import examples_run as ex

NAME = 'test_release_examples_cascade'
MODELS = ['yolox-m-coco-onnx', 'yolo26npose-coco-onnx']
IMAGE = ex.ASSETS / 'dancing_frame_t15_480p.jpg'
STREAMS, FRAMES = 2, 100


def body() -> None:
    """Run the two-stage cascade scenario (yolox-m detector plus yolo26npose) and tear the pipeline down afterwards.

    Raises:
        StepFailed: If the environment is incomplete, the test image is missing, a helper command fails, or the demo reports no detections or keypoints.
    """
    ex.require_env()
    if not IMAGE.is_file():
        raise ex.StepFailed(f'{IMAGE} is missing')
    compiled = None
    with tempfile.TemporaryDirectory(prefix='examples_cascade_') as tmp:
        try:
            compiled, endpoints = ex.launch_vision('cascade', ['--secondary-meta-key-override'], MODELS, Path(tmp))
            stats = ex.demo(endpoints, IMAGE, STREAMS, FRAMES)
            ex.require_positive(stats, 'detections', 'keypoints')
        finally:
            if compiled is not None:
                ex.helper('down', str(compiled), what='helper down')


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
