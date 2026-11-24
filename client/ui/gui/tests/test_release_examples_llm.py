#!/usr/bin/env python3

"""Release test for the LLM example: serve qwen3-0.6b through the helper CLI and run three text requests against it.

Needs HOST_SERVER_URL and HOST_SERVER_API_KEY. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

from utils import examples_run as ex

NAME = 'test_release_examples_llm'
ARTIFACT, PORT = 'qwen3-0.6b', 50070


def body() -> None:
    """Start a vLLM session for the artifact and run the text demo three times.

    Raises:
        StepFailed: If the environment is incomplete or the session checks fail.
    """
    ex.require_env()
    ex.vllm_session(ARTIFACT, PORT, 'llm', 'Name three primary colors.', [], loops=3)


if __name__ == '__main__':
    raise SystemExit(ex.run_test(NAME, body))
