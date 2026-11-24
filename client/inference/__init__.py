"""Python client library for the Axelera inference server.

Exports the vision clients (AxVisionClient, AsyncAxVisionClient) and the generic cross-process
clients they build on (AxInferClient, AsyncAxInferClient).

Note:
    Importing this package prepends the 'generated' directory next to it to sys.path so that
    the protobuf stubs (axinfer.v1) can be imported; run gen_stubs.sh to create them.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

from ._client import AsyncAxInferClient, AxInferClient
from .vision import AsyncAxVisionClient, AxVisionClient

__all__ = [
    "AxInferClient",
    "AsyncAxInferClient",
    "AxVisionClient",
    "AsyncAxVisionClient",
]
