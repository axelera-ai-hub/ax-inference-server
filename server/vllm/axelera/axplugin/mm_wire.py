"""Helpers that pack images and chat messages into tensors and unpack them again.

vLLM carries the tensors through its multimodal passthrough fields; see axplugin.multimodal.
"""

from __future__ import annotations

import json

import numpy as np
import torch


def encode_image(image: object) -> torch.Tensor:

    """Convert an image to a uint8 tensor so it can pass through vLLM's multimodal pipeline.

    Args:
        image (object): A PIL-style image (converted to RGB if it has convert()) or an array-like of uint8 pixels.

    Returns:
        torch.Tensor: uint8 tensor of the pixel data (height x width x channels for RGB).
    """
    if hasattr(image, "convert"):
        image = image.convert("RGB")
    return torch.from_numpy(np.asarray(image, dtype=np.uint8))


def decode_image(tensor: torch.Tensor) -> np.ndarray:
    """Return the image tensor as a NumPy array (inverse of encode_image)."""
    return tensor.numpy()


def encode_messages(messages: object) -> torch.Tensor:
    """Serialize chat messages to JSON and return the UTF-8 bytes as a uint8 tensor.

    Args:
        messages (object): JSON-serializable chat messages.
    """
    data = bytearray(json.dumps(messages).encode("utf-8"))
    return torch.frombuffer(data, dtype=torch.uint8)


def decode_messages(tensor: torch.Tensor) -> object:
    """Return the chat messages stored in a uint8 tensor (inverse of encode_messages)."""
    return json.loads(tensor.numpy().tobytes().decode("utf-8"))
