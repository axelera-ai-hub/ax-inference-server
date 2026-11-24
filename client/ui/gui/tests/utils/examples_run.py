"""Helpers for release tests that drive the client examples through the helper CLI and the demo scripts.

Each helper runs a subprocess in the examples directory and raises StepFailed on an unexpected exit code or missing output.
run_test() turns that into a PASS/FAIL exit status.

Note:
    HOST_SERVER_URL and HOST_SERVER_API_KEY must be set (see require_env).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import release_gate

CLIENT = Path(__file__).resolve().parents[4]
EXAMPLES = CLIENT / 'examples'
ASSETS = CLIENT / 'assets' / 'test_images'
MAX_POWER_LIMIT_W = '100'


class StepFailed(Exception):
    """Raised when a test step fails; its message is logged as the failure reason."""
    pass


def log(msg: str) -> None:
    """Print a message prefixed with the current time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def passed(msg: str) -> None:
    """Log a message prefixed with "PASS:"."""
    log(f'PASS: {msg}')


def require_env() -> None:
    """Check that the host server environment variables are set.

    Raises:
        StepFailed: If HOST_SERVER_URL or HOST_SERVER_API_KEY is missing or empty.
    """
    missing = [v for v in ('HOST_SERVER_URL', 'HOST_SERVER_API_KEY') if not os.environ.get(v)]
    if missing:
        raise StepFailed(f'{" and ".join(missing)} must be set')


def run(cmd: list[str], what: str, expect_rc: int = 0) -> subprocess.CompletedProcess:
    """Run a command in the examples directory, echoing its stdout and stderr.

    Args:
        cmd (list[str]): Command and arguments.
        what (str): Description used in the failure message.
        expect_rc (int, optional): Expected exit code. Defaults to 0.

    Returns:
        subprocess.CompletedProcess: The finished process with captured text output.

    Raises:
        StepFailed: If the exit code differs from expect_rc.
    """
    log(f'$ {" ".join(cmd[1:] if cmd[0] == sys.executable else cmd)}')
    res = subprocess.run(cmd, cwd=EXAMPLES, capture_output=True, text=True)
    for stream in (res.stdout, res.stderr):
        if stream.strip():
            print(stream.rstrip(), flush=True)
    if res.returncode != expect_rc:
        raise StepFailed(f'{what}: exit code {res.returncode}, expected {expect_rc}')
    return res


def helper(*args: str, what: str | None = None, expect_rc: int = 0) -> subprocess.CompletedProcess:
    """Run "python -m helper" with the given arguments.

    Args:
        *args (str): Arguments for the helper CLI.
        what (str | None, optional): Failure description. Defaults to "helper <first argument>".
        expect_rc (int, optional): Expected exit code. Defaults to 0.

    Returns:
        subprocess.CompletedProcess: The finished process.
    """
    return run([sys.executable, '-m', 'helper', *args], what or f'helper {args[0]}', expect_rc)


def example(script: str, *args: str, expect_rc: int = 0) -> subprocess.CompletedProcess:
    """Run an example script with the current Python interpreter.

    Args:
        script (str): Script path relative to the examples directory.
        *args (str): Script arguments.
        expect_rc (int, optional): Expected exit code. Defaults to 0.

    Returns:
        subprocess.CompletedProcess: The finished process.
    """
    return run([sys.executable, script, *args], script, expect_rc)


def first_healthy_device(attempts: int = 4, wait_s: float = 20.0) -> int:
    """Ask the helper for the first healthy device, retrying while a previous run may still hold it.

    Args:
        attempts (int, optional): Maximum tries. Defaults to 4.
        wait_s (float, optional): Seconds to wait between tries. Defaults to 20.0.

    Returns:
        int: Index of the healthy device (last line of the helper output).

    Raises:
        StepFailed: If no healthy device is found after the last attempt.
    """
    for attempt in range(1, attempts + 1):
        try:
            return int(helper('devices', '--first', what='no healthy device').stdout.strip().splitlines()[-1])
        except StepFailed:
            if attempt == attempts:
                raise
            log(f'no healthy device (attempt {attempt}/{attempts}); the previous run may still be releasing it, retrying in {wait_s:.0f} s')
            time.sleep(wait_s)
    raise AssertionError('unreachable')


def prepare_host(models: list[str]) -> int:
    """Stop all pipelines, pick a healthy device, try to set its power limit and provision models.

    A failed power-limit call is logged, not raised.

    Args:
        models (list[str]): Prebuilt model names to provision on the device.

    Returns:
        int: The selected device index.
    """
    require_env()
    helper('stop-all')
    device = first_healthy_device()
    passed(f'using device {device}')
    power = subprocess.run([sys.executable, '-m', 'helper', 'power', 'set', '--device', str(device), '--limit', MAX_POWER_LIMIT_W],
                           cwd=EXAMPLES, capture_output=True, text=True)
    log(f'power limit {MAX_POWER_LIMIT_W} W on device {device}: ' + ('set' if power.returncode == 0 else
        f'not changed (the device may not support it): {power.stderr.strip()[:120]}'))
    for model in models:
        helper('models', 'provision', model, '--device', str(device), what=f'provision {model}')
    passed(f'models ready: {", ".join(models)}')
    return device


def endpoints_from(stdout: str) -> list[str]:
    """Extract HOST:PORT endpoint lines from the output of "helper up".

    Args:
        stdout (str): Captured output.

    Returns:
        list[str]: Every line that consists solely of a HOST:PORT endpoint.

    Raises:
        StepFailed: If no endpoint line is present.
    """
    found = [line.strip() for line in stdout.splitlines() if re.fullmatch(r'[\w.\-]+:\d+', line.strip())]
    if not found:
        raise StepFailed(f'no HOST:PORT endpoint in the output of helper up: {stdout!r}')
    return found


def summary(stdout: str) -> dict[str, float]:
    """Parse the last "summary: key=value ..." line printed by vision_demo.py.

    Args:
        stdout (str): Captured output of vision_demo.py.

    Returns:
        dict[str, float]: The summary values keyed by name.

    Raises:
        StepFailed: If there is no summary line.
    """
    lines = [ln for ln in stdout.splitlines() if ln.startswith('summary: ')]
    if not lines:
        raise StepFailed('vision_demo.py printed no "summary:" line')
    return {k: float(v) for k, v in (kv.split('=') for kv in lines[-1][len('summary: '):].split())}


def check_demo(stats: dict[str, float], streams: int, frames: int) -> None:
    """Validate demo statistics against the expected workload.

    Args:
        stats (dict[str, float]): Parsed summary with at least errors, frames, fps and latency_p50/p95/p99.
        streams (int): Number of streams that were run.
        frames (int): Frames per stream.

    Raises:
        StepFailed: If any inference errors occurred or the frame count differs from streams * frames.
    """
    expected = streams * frames
    if stats['errors'] != 0:
        raise StepFailed(f'{int(stats["errors"])} inference error(s)')
    if stats['frames'] != expected:
        raise StepFailed(f'{int(stats["frames"])} frames completed, expected {expected}')
    passed(f'{int(stats["frames"])} frames, 0 errors, {stats["fps"]:.1f} fps, '
           f'latency p50/p95/p99 {stats["latency_p50"]:.0f}/{stats["latency_p95"]:.0f}/{stats["latency_p99"]:.0f} ms')


def launch_vision(kind: str, extra: list[str], models: list[str], workdir: Path) -> tuple[Path, list[str]]:
    """Prepare the host, generate a vision config, bring the pipeline up and wait for it to be ready.

    Args:
        kind (str): Config kind passed to "helper config"; also the YAML file stem.
        extra (list[str]): Additional arguments for "helper config".
        models (list[str]): Prebuilt models to provision.
        workdir (Path): Directory for the generated YAML and the compiled output.

    Returns:
        tuple[Path, list[str]]: The compiled output directory and the pipeline endpoints.
    """
    device = prepare_host(models)
    cfg = workdir / f'{kind}.yaml'
    helper('config', kind, '--devices', str(device), '--pin', *extra, '-o', str(cfg))
    compiled = workdir / 'compiled'
    endpoints = endpoints_from(helper('up', 'vision', str(cfg), '--output-dir', str(compiled), what='helper up vision').stdout)
    helper('status', str(compiled), '--wait', '60', what='pipeline status')
    passed(f'pipeline(s) up on {", ".join(endpoints)}')
    return compiled, endpoints


def demo(endpoints: list[str], source: Path, streams: int, frames: int, *extra: str) -> dict[str, float]:
    """Run vision_demo.py against the given endpoints and validate the result.

    Args:
        endpoints (list[str]): HOST:PORT endpoints.
        source (Path): Video or image source.
        streams (int): Number of streams.
        frames (int): Frames per stream.
        *extra (str): Additional vision_demo.py arguments.

    Returns:
        dict[str, float]: The parsed summary statistics.
    """
    res = example('vision_demo.py', '--endpoints', ','.join(endpoints), '--source', str(source),
                  '--streams', str(streams), '--frames', str(frames), *extra)
    stats = summary(res.stdout)
    check_demo(stats, streams, frames)
    return stats


def require_positive(stats: dict[str, float], *keys: str) -> None:
    """Require the named statistics to be greater than zero.

    Args:
        stats (dict[str, float]): Parsed demo summary.
        *keys (str): Statistic names to check.

    Raises:
        StepFailed: If any named statistic is zero or negative.
    """
    for key in keys:
        if stats[key] <= 0:
            raise StepFailed(f'vision_demo.py reported {int(stats[key])} {key}, expected more than 0')
        passed(f'{int(stats[key])} {key}')


def vllm_session(artifact: str, port: int, kind: str, prompt: str, images: list[Path], loops: int, max_new_tokens: int = 32) -> None:
    """Serve a vLLM artifact, run vllm_demo.py against it, validate the decode statistics and shut it down.

    The server is always stopped with "helper vllm down", even on failure.

    Args:
        artifact (str): vLLM artifact name.
        port (int): Port to serve on.
        kind (str): vllm_demo.py mode argument.
        prompt (str): Prompt text.
        images (list[Path]): Image files to send; empty for text-only.
        loops (int): Number of requests; must equal the request count in the average line.
        max_new_tokens (int, optional): Token limit per request. Defaults to 32.

    Raises:
        StepFailed: If no URL or average line is printed, the request count differs, first-token latency or
            throughput is not positive, or the model returned no text.
    """
    device = prepare_host([])
    name = re.sub(r'[^A-Za-z0-9_-]', '-', artifact)
    up = helper('vllm', 'up', '--artifact', artifact, '--port', str(port), '--device', str(device), what='helper vllm up')
    try:
        url = next((ln.strip() for ln in up.stdout.splitlines() if ln.strip().startswith('http://')), '')
        if not url:
            raise StepFailed(f'helper vllm up printed no URL: {up.stdout!r}')
        passed(f'{artifact} serving on {url}')
        args = ['vllm_demo.py', kind, '--url', url, '--prompt', prompt, '--max-new-tokens', str(max_new_tokens), '--loop', str(loops)]
        if images:
            args += ['--images', ','.join(str(i) for i in images)]
        res = example(*args)
        m = re.search(r'average over (\d+) request\(s\): first token ([\d.]+) ms, ([\d.]+) tokens/s', res.stdout)
        if not m:
            raise StepFailed('vllm_demo.py printed no average line')
        n, ttft_ms, tps = int(m.group(1)), float(m.group(2)), float(m.group(3))
        if n != loops:
            raise StepFailed(f'{n} requests completed, expected {loops}')
        if ttft_ms <= 0 or tps <= 0:
            raise StepFailed(f'first token {ttft_ms} ms, {tps} tokens/s: not a working decode')
        if not res.stdout.split('average over')[0].strip():
            raise StepFailed('the model returned no text')
        passed(f'{n} request(s): first token {ttft_ms:.0f} ms, {tps:.1f} tokens/s')
    finally:
        helper('vllm', 'down', '--name', name, what='helper vllm down')


def run_test(name: str, body) -> int:
    """Run a test body and convert the outcome to a process exit status.

    Args:
        name (str): Test name for the verdict line.
        body (Callable[[], None]): The test steps.

    Returns:
        int: 0 if body completed (after printing "ALL STEPS PASSED" and the release_gate verdict), 1 if it raised.
    """
    try:
        body()
    except Exception as exc:
        log(f'FAIL: {exc}')
        print(f'{name}: FAIL')
        return 1
    print('ALL STEPS PASSED')
    release_gate.verdict(name)
    return 0
