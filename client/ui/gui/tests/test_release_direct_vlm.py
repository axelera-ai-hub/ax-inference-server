#!/usr/bin/env python3

"""Release test that streams text and multi-image chat completions straight from the running vLLM server with httpx, bypassing the helper CLI.

Needs HOST_SERVER_URL (and HOST_SERVER_API_KEY) to locate a running instance of smolvlm2-256m-video-instruct.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path

import httpx

from utils.host_server_prep import require_vllm_artifacts


# Host server base URL and API key, used only to discover the vLLM instance port.
HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')
IMAGE_DIR = Path(__file__).resolve().parents[3] / 'assets' / 'test_images'
CHAT_IMAGE_FILENAMES = ('dancing_frame_t5_480p.jpg', 'dancing_frame_t15_480p.jpg')
JOKE_PROMPT = 'Tell me a joke.'
DESCRIBE_PROMPT = 'Describe the images.'
CHAT_TIMEOUT_S = 120.0


def log(msg: str) -> None:
    """Print a message prefixed with the local time."""
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def discover_vllm_base_url() -> str:
    """Find the base URL of the first running vLLM instance reported by the host server.

    Queries `GET {HOST_SERVER_URL}/api/v1/vllm/status` with the API key and builds `http://<host>:<port>` from the host of HOST_SERVER_URL and the instance's port.

    Returns:
        str: The base URL of the first running instance.

    Raises:
        RuntimeError: If HOST_SERVER_URL is unset or no instance is running.
        httpx.HTTPStatusError: If the status request returns an error status.
    """
    if not HOST_SERVER_URL:
        raise RuntimeError('HOST_SERVER_URL not set in environment')
    r = httpx.get(f'{HOST_SERVER_URL}/api/v1/vllm/status',
                  headers={'X-API-Key': HOST_SERVER_API_KEY}, timeout=10.0)
    r.raise_for_status()
    instances = r.json().get('instances', [])
    running = [i for i in instances if i.get('running')]
    if not running:
        raise RuntimeError(f'no running vLLM instance found via /api/v1/vllm/status: {r.json()}')
    inst = running[0]
    host = httpx.URL(HOST_SERVER_URL).host
    base_url = f'http://{host}:{inst["port"]}'
    log(f'PASS: discovered running vLLM instance {inst["name"]!r} on port {inst["port"]} -> {base_url}')
    return base_url


def load_images() -> list[bytes]:
    """Read the chat test images from IMAGE_DIR.

    Returns:
        list[bytes]: Raw JPEG bytes, in the order of CHAT_IMAGE_FILENAMES.

    Raises:
        RuntimeError: If a test image does not exist.
    """
    images = []
    for fn in CHAT_IMAGE_FILENAMES:
        path = IMAGE_DIR / fn
        if not path.is_file():
            raise RuntimeError(f'test image not found: {path}')
        images.append(path.read_bytes())
    return images


def build_text_message(prompt: str) -> list[dict]:
    """Build a single-turn user chat message list from a text prompt."""
    return [{'role': 'user', 'content': prompt}]


def build_image_message(images: list[bytes], prompt: str, mime: str = 'image/jpeg') -> list[dict]:
    """Build a single-turn user chat message with inline base64 images followed by a text prompt.

    Args:
        images (list[bytes]): Raw image bytes, each sent as a `data:` URL.
        prompt (str): Text appended after the images.
        mime (str, optional): MIME type for the data URLs. Defaults to 'image/jpeg'.

    Returns:
        list[dict]: One user message whose content is the image parts plus the text part.
    """
    content = [
        {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{base64.b64encode(img).decode()}'}}
        for img in images
    ]
    content.append({'type': 'text', 'text': prompt})
    return [{'role': 'user', 'content': content}]


async def raw_chat_stream(base_url: str, messages: list[dict], *, label: str) -> str:
    """Stream one chat completion from a vLLM server and return the full reply text.

    Picks the first model listed by `/v1/models`, posts the messages to `/v1/chat/completions` with `stream` enabled, concatenates the delta contents and logs the time to first chunk (TTFT).

    Args:
        base_url (str): Base URL of the OpenAI-compatible server.
        messages (list[dict]): Chat messages in OpenAI format.
        label (str): Tag used in log and error messages.

    Returns:
        str: The concatenated reply text.

    Raises:
        RuntimeError: If the response status is not 200, a streamed chunk has no `choices`, or the reply is empty.
        httpx.HTTPStatusError: If listing models fails.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=CHAT_TIMEOUT_S,
                                  headers={'Authorization': 'Bearer EMPTY'}) as http:
        model_resp = await http.get('/v1/models')
        model_resp.raise_for_status()
        model = model_resp.json()['data'][0]['id']
        payload = {'model': model, 'messages': messages, 'stream': True}
        t_start = time.monotonic()
        t_first = None
        text = ''
        async with http.stream('POST', '/v1/chat/completions', json=payload) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode('utf-8', 'replace')
                raise RuntimeError(f'[{label}] HTTP {resp.status_code}: {body[:2000]}')
            async for line in resp.aiter_lines():
                if not line.startswith('data: '):
                    continue
                data = line[len('data: '):]
                if data == '[DONE]':
                    break
                parsed = json.loads(data)
                if 'choices' not in parsed:
                    raise RuntimeError(f'[{label}] mid-stream error chunk: {parsed}')
                if t_first is None:
                    t_first = time.monotonic()
                delta = parsed['choices'][0].get('delta', {})
                content = delta.get('content')
                if content:
                    text += content
        if not text:
            raise RuntimeError(f'[{label}] empty response')
        ttft = (t_first or time.monotonic()) - t_start
        log(f'PASS: [{label}] raw-httpx reply received -- TTFT {ttft:.2f}s, {len(text)} chars')
        return text


async def run_raw_mode(base_url: str, images: list[bytes]) -> None:
    """Send the joke prompt as text and the describe prompt with the images as two independent streaming requests.

    Args:
        base_url (str): Base URL of the vLLM server.
        images (list[bytes]): Raw image bytes attached to the describe request.
    """
    log('--- raw httpx streaming chat ---')
    await raw_chat_stream(base_url, build_text_message(JOKE_PROMPT), label='raw-joke')
    await raw_chat_stream(base_url, build_image_message(images, DESCRIBE_PROMPT), label='raw-describe')



async def main_async(repeat: int) -> int:
    """Run the raw-streaming scenario `repeat` times and report the outcome.

    Failures in an iteration are collected and printed at the end rather than stopping the loop.

    Args:
        repeat (int): Number of iterations.

    Returns:
        int: 0 if every iteration passed, 1 otherwise.
    """
    base_url = discover_vllm_base_url()
    images = load_images()
    failures: list[str] = []
    for i in range(repeat):
        if repeat > 1:
            log(f'=== iteration {i + 1}/{repeat} ===')
        try:
            await run_raw_mode(base_url, images)
        except Exception as exc:
            log(f'FAIL: {exc}')
            failures.append(str(exc))
    if failures:
        print(f'{len(failures)} FAILURE(S):')
        for f in failures:
            print(f' - {f}')
        print('test_release_direct_vlm: FAIL')
        return 1
    print('ALL STEPS PASSED')
    print('test_release_direct_vlm: PASS')
    return 0


def main() -> int:
    """Parse the command line, check the model artifact is deployed, and run the test.

    Returns:
        int: 0 when the test passes or is skipped because the artifact is not deployed, 1 on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    if not require_vllm_artifacts('test_release_direct_vlm', ['smolvlm2-256m-video-instruct']):
        return 0
    return asyncio.run(main_async(args.repeat))


if __name__ == '__main__':
    raise SystemExit(main())
