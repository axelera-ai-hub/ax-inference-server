#!/usr/bin/env python3

"""Release test for the VLM example: serve smolvlm2-256m-video-instruct through the helper CLI and run three image-description requests.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

from utils import examples_run as ex

NAME = 'test_release_examples_vlm'
ARTIFACT, PORT = 'smolvlm2-256m-video-instruct', 50071
IMAGES = [ex.ASSETS / 'dancing_frame_t15_480p.jpg', ex.ASSETS / 'traffic_frame_480p.jpg']


def body() -> None:
    """Check that the test images exist, then start a vLLM session and run the image demo three times.

    Raises:
        StepFailed: If the environment is incomplete, an image is missing, or the session checks fail.
    """
    ex.require_env()
    for image in IMAGES:
        if not image.is_file():
            raise ex.StepFailed(f'{image} is missing')
    ex.vllm_session(ARTIFACT, PORT, 'vlm', 'Describe each image in one sentence.', IMAGES, loops=3)


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
