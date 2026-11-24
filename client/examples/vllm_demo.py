"""Send a prompt (and optionally images) to a running vLLM server and report time to first token and tokens per second.

Run it with `llm` or `vlm` plus --url and --prompt; a pre-flight check refuses requests that cannot fit the model context.
"""


from __future__ import annotations

import argparse
import asyncio
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inference.llm_vlm import AsyncAxLlmClient, AsyncAxVlmClient

MAX_IMAGES = 8
PATCH_PX = 28


def parse_args(argv=None):
    """Parse the command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('kind', choices=['llm', 'vlm'])
    p.add_argument('--url', required=True, help='vLLM server, e.g. http://host:8000')
    p.add_argument('--prompt', required=True)
    p.add_argument('--images', help='vlm: comma-separated image files (up to 8)')
    p.add_argument('--resize', type=int, default=0, metavar='N', help='vlm: resize every image to a square N x N before sending '
                   '(default 0 = off, images are sent as they are). Fewer pixels, fewer prompt tokens')
    p.add_argument('--max-new-tokens', type=int, default=256, help='limit on the answer length in tokens (default 256); '
                   'it also counts against the model context in the pre-flight check')
    p.add_argument('--thinking', action='store_true', help='per-request thinking mode (the server default otherwise)')
    p.add_argument('--loop', type=int, default=1, help='send the request N times and report averages (default 1)')
    return p.parse_args(argv)


async def one_request(client, args, images: list[bytes]) -> dict:
    """Stream one request and time it.

    Args:
        client: An AsyncAxLlmClient or AsyncAxVlmClient, matching `args.kind`.
        args (argparse.Namespace): Parsed arguments.
        images (list[bytes]): Encoded images; used for vlm only.

    Returns:
        dict: `text`, `ttft_s`, `total_s`, `tokens` (counted by the server on the final text) and `tokens_per_s` (over the decode phase after the first token).

    Raises:
        RuntimeError: If the server returned no tokens.
    """
    kwargs = {'max_new_tokens': args.max_new_tokens, 'enable_thinking': True if args.thinking else None}
    start = time.monotonic()
    stream = client.infer_stream(images, args.prompt, **kwargs) if args.kind == 'vlm' else client.infer_stream(args.prompt, **kwargs)
    first = None
    parts: list[str] = []
    async for delta in stream:
        if first is None:
            first = time.monotonic()
        parts.append(delta)
    end = time.monotonic()
    text = ''.join(parts)
    if first is None:
        raise RuntimeError('the server returned no tokens')
    tokens = await client.count_tokens(text) if text else 0
    decode_s = max(end - first, 1e-6)
    return {'text': text, 'ttft_s': first - start, 'total_s': end - start, 'tokens': tokens, 'tokens_per_s': tokens / decode_s}


def server_context_length(url: str) -> int | None:
    """Find the context length of the vLLM server at a URL.

    Asks the host server first when HOST_SERVER_URL and HOST_SERVER_API_KEY are set, then the vLLM /v1/models endpoint.

    Args:
        url (str): Base URL of the vLLM server.

    Returns:
        int | None: The context length, or None if it could not be determined.
    """
    port = urlparse(url).port
    if os.environ.get('HOST_SERVER_URL') and os.environ.get('HOST_SERVER_API_KEY'):
        try:
            from helper import server
            for inst in server.vllm_status():
                if inst['port'] == port and inst.get('context_length'):
                    return int(inst['context_length'])
        except Exception:
            pass
    try:
        import httpx
        data = httpx.get(url.rstrip('/') + '/v1/models', timeout=10.0).json()['data'][0]
        return int(data['max_model_len']) if data.get('max_model_len') else None
    except Exception:
        return None


def _sizes(args, images: list[bytes]) -> list[tuple[int, int]]:
    """Return the (width, height) each image will have in the prompt, which is N x N when --resize is set."""
    import cv2
    import numpy as np
    sizes = []
    for raw in images:
        h, w = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR).shape[:2]
        sizes.append((args.resize, args.resize) if args.resize else (w, h))
    return sizes


async def preflight(client, args, images: list[bytes]) -> int:
    """Estimate the prompt size and refuse requests that cannot fit the context.

    Tokenizes the text on the server. For vlm, image tokens are estimated as one per PATCH_PX x PATCH_PX patch, which is a lower bound. Prints the estimate to stderr.

    Args:
        client: The LLM or VLM client.
        args (argparse.Namespace): Parsed arguments.
        images (list[bytes]): Encoded images; used for vlm only.

    Returns:
        int: 0 if the request may be sent, 2 if it needs more tokens than the context.
    """
    context = server_context_length(args.url)
    payload = {'model': await client._resolve_model(),
               'messages': client._build_messages(images, args.prompt) if args.kind == 'vlm' else client._build_messages(args.prompt)}
    response = await client._http.post('/tokenize', json=payload)
    response.raise_for_status()
    text_tokens = int(response.json()['count'])
    guess = sum(math.ceil(w / PATCH_PX) * math.ceil(h / PATCH_PX) for w, h in _sizes(args, images)) if args.kind == 'vlm' else 0
    total = text_tokens + guess + args.max_new_tokens
    detail = f'{text_tokens} text' + (f' + {guess} image (GUI estimate, a lower bound)' if args.kind == 'vlm' else '')
    print(f'pre-flight: {detail} + {args.max_new_tokens} max new tokens = {total} of {context or "unknown"} context', file=sys.stderr)
    if context and total > context:
        hint = 'use fewer images, a smaller --resize, ' if args.kind == 'vlm' else ''
        print(f'ERROR: the request needs at least {total} tokens but the model context is {context}. Not sent, it would crash '
              f'the server. Shorten the prompt, {hint}or lower --max-new-tokens.', file=sys.stderr)
        return 2
    if args.kind == 'vlm':
        print('WARNING: the server does not report image tokens; if the images cost more than the estimate the engine can '
              'still fail (see --resize).', file=sys.stderr)
    return 0


async def main_async(args, images: list[bytes]) -> int:
    """Run the pre-flight check, send --loop requests and print the results.

    Args:
        args (argparse.Namespace): Parsed arguments.
        images (list[bytes]): Encoded images; empty for llm.

    Returns:
        int: 0 on success, 1 on a request failure, 2 if the pre-flight check refused the request.
    """
    if args.kind == 'vlm':
        client = AsyncAxVlmClient(args.url, image_resize=(args.resize, args.resize) if args.resize else None, timeout=300.0)
    else:
        client = AsyncAxLlmClient(args.url, timeout=300.0)
    runs = []
    try:
        rc = await preflight(client, args, images)
        if rc:
            return rc
        for i in range(args.loop):
            r = await one_request(client, args, images)
            runs.append(r)
            if i == 0:
                print(r['text'].strip())
            print(f'[{i + 1}/{args.loop}] first token {r["ttft_s"] * 1000:.0f} ms, {r["tokens"]} tokens, '
                  f'{r["tokens_per_s"]:.1f} tokens/s, total {r["total_s"]:.2f} s', file=sys.stderr)
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        await client.close()
    print(f'average over {len(runs)} request(s): first token {statistics.mean(r["ttft_s"] for r in runs) * 1000:.0f} ms, '
          f'{statistics.mean(r["tokens_per_s"] for r in runs):.1f} tokens/s')
    return 0


def main(argv=None) -> int:
    """Run the demo.

    Args:
        argv (list[str], optional): Arguments to parse. Defaults to sys.argv[1:].

    Returns:
        int: 0 on success, 1 on a request failure, 2 on invalid arguments.
    """
    args = parse_args(argv)
    if args.loop < 1:
        print('ERROR: --loop must be >= 1', file=sys.stderr)
        return 2
    images: list[bytes] = []
    if args.kind == 'vlm':
        paths = [x for x in (args.images or '').split(',') if x.strip()]
        if not paths:
            print('ERROR: vlm needs --images a.jpg[,b.jpg...]', file=sys.stderr)
            return 2
        if len(paths) > MAX_IMAGES:
            print(f'ERROR: at most {MAX_IMAGES} images per prompt, got {len(paths)}', file=sys.stderr)
            return 2
        missing = [p for p in paths if not Path(p).is_file()]
        if missing:
            print(f'ERROR: image(s) not found: {missing}', file=sys.stderr)
            return 2
        images = [Path(p).read_bytes() for p in paths]
    elif args.images:
        print('ERROR: --images is for vlm', file=sys.stderr)
        return 2
    return asyncio.run(main_async(args, images))


if __name__ == '__main__':
    raise SystemExit(main())
