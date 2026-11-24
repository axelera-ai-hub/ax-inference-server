#!/usr/bin/env python3

"""Release test for the helper CLI: health, models, power, pin, config and compile commands against a real host.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from utils import examples_run as ex

NAME = 'test_release_examples_helper'
MODEL = 'yolox-m-coco-onnx'


def body() -> None:
    """Exercise each helper subcommand once and check its observable result.

    The final step runs `helper vllm up` with no arguments and expects a usage error (exit code 2).

    Raises:
        StepFailed: If any helper command exits with an unexpected code, the model is not listed, or config/compile produce no usable output.
    """
    ex.require_env()
    ex.helper('health')
    ex.helper('stop-all')
    device = ex.first_healthy_device()
    ex.passed(f'first healthy device: {device}')
    listing = ex.helper('models', 'list').stdout
    if MODEL not in listing:
        raise ex.StepFailed(f'{MODEL} is not in `helper models list`')
    ex.passed(f'models list names {MODEL}')
    ex.helper('models', 'provision', MODEL, '--device', str(device))
    ex.helper('power', 'get', '--device', str(device))
    ex.helper('pin', '--devices', str(device), '--num-devices', '1')
    with tempfile.TemporaryDirectory(prefix='examples_helper_') as tmp:
        cfg, out = Path(tmp) / 'iso.yaml', Path(tmp) / 'compiled'
        ex.helper('config', 'isovision', '--model', MODEL, '--devices', str(device), '-o', str(cfg))
        if not cfg.is_file() or MODEL not in cfg.read_text():
            raise ex.StepFailed('helper config wrote no usable YAML')
        ex.helper('compile', str(cfg), '--output-dir', str(out))
        if not any(out.iterdir()):
            raise ex.StepFailed('helper compile produced no files')
        ex.passed('config + compile produced specs')
    ex.helper('vllm', 'up', what='usage error', expect_rc=2)


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
