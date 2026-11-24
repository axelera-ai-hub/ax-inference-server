"""HTTP clients for LLM and VLM servers that expose an OpenAI-compatible chat API.

Provides AxLlmClient and AxVlmClient (blocking) and AsyncAxLlmClient and AsyncAxVlmClient
(asyncio, with streaming), plus the ChatInferResult returned by non-streaming calls.
"""
from __future__ import annotations

import base64
import dataclasses
import io
import json
from typing import Any, AsyncIterator, Optional, Union

import httpx

_DEFAULT_TIMEOUT = 60.0

Message = dict[str, Any]


@dataclasses.dataclass
class ChatInferResult:
    """Result of one chat completion request.

    Attributes:
        answer (str): Text of the first choice's message.
        finish_reason (Optional[str]): Why generation stopped, e.g. 'stop' or 'length'.
        prompt_tokens (Optional[int]): Prompt token count from the usage block, if reported.
        completion_tokens (Optional[int]): Generated token count from the usage block, if reported.
        request_id (Optional[str]): Caller-supplied id; not sent to the server.
        raw (dict): Full decoded JSON response.
    """

    answer: str
    finish_reason: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    request_id: Optional[str]
    raw: dict


class _ChatPayloadMixin:
    """Shared helpers for building OpenAI-style chat completion payloads and parsing replies; used by the sync and async clients."""

    base_url: str
    _model: Optional[str]

    def _build_messages(self, *args, **kwargs) -> list[Message]:
        """Convert the caller's inputs to chat messages; implemented by subclasses."""
        raise NotImplementedError

    def _build_payload(
        self,
        messages: list[Message],
        *,
        model: str,
        max_new_tokens: Optional[int],
        temperature: Optional[float],
        enable_thinking: Optional[bool],
    ) -> dict:
        """Build the JSON body for /v1/chat/completions, including max_tokens, temperature and chat_template_kwargs.enable_thinking only when they are not None."""
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if max_new_tokens is not None:
            payload["max_tokens"] = max_new_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
        return payload

    @staticmethod
    def _parse_response(data: dict, request_id: Optional[str]) -> ChatInferResult:
        """Convert a chat completion JSON response into a ChatInferResult, using the first choice."""
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        return ChatInferResult(
            answer=choice["message"]["content"],
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            request_id=request_id,
            raw=data,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise if the HTTP status is not 200.

        Raises:
            RuntimeError: With the status code, URL and the first 2000 characters of the body.
        """
        if response.status_code != 200:
            raise RuntimeError(
                f"infer() failed: HTTP {response.status_code} from {response.request.url}: "
                f"{response.text[:2000]}"
            )

    @staticmethod
    def _image_bytes_to_data_url(image_bytes: bytes, mime_type: str) -> str:
        """Encode image bytes as a base64 'data:' URL."""
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"


_MIME_TO_PIL_FORMAT = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def _resize_image_bytes(image_bytes: bytes, size: tuple[int, int], mime_type: str) -> bytes:
    """Resize an encoded image and re-encode it in the same format.

    Args:
        image_bytes (bytes): Encoded image.
        size (tuple[int, int]): Target (width, height); the aspect ratio is not preserved.
        mime_type (str): Image MIME type; unknown types are written as JPEG.

    Returns:
        bytes: The resized, re-encoded image. JPEG output is converted to RGB first.
    """
    from PIL import Image

    fmt = _MIME_TO_PIL_FORMAT.get(mime_type.lower(), "JPEG")
    with Image.open(io.BytesIO(image_bytes)) as img:
        if fmt == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")
        resized = img.resize(size)
        buf = io.BytesIO()
        resized.save(buf, format=fmt)
        return buf.getvalue()


class _HttpInferClient(_ChatPayloadMixin):
    """Blocking HTTP client for an OpenAI-compatible chat server.

    Uses a persistent httpx.Client. The model name is fetched from /v1/models on first use when not
    given. Supports use as a context manager.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: Optional[str] = None,
        api_key: str = "EMPTY",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Create the HTTP client.

        Args:
            base_url (str): Server base URL; a trailing slash is removed.
            model (Optional[str], optional): Model name to send. If None, the first model listed by /v1/models is used.
            api_key (str, optional): Bearer token for the Authorization header. Defaults to 'EMPTY'.
            timeout (float, optional): Default request timeout in seconds. Defaults to 60.0.
        """
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> "_HttpInferClient":
        """Return the client itself."""
        return self

    def __exit__(self, *_) -> None:
        """Close the client."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def _resolve_model(self) -> str:
        """Return the model name, querying /v1/models once and caching the first entry if none was given."""
        if self._model is None:
            response = self._http.get("/v1/models")
            self._raise_for_status(response)
            self._model = response.json()["data"][0]["id"]
        return self._model

    def _chat(
        self,
        messages: list[Message],
        *,
        max_new_tokens: Optional[int],
        temperature: Optional[float],
        enable_thinking: Optional[bool],
        request_id: Optional[str],
        timeout: float,
    ) -> ChatInferResult:
        """Send a chat completion request and parse the reply.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        payload = self._build_payload(
            messages, model=self._resolve_model(), max_new_tokens=max_new_tokens,
            temperature=temperature, enable_thinking=enable_thinking,
        )
        response = self._http.post("/v1/chat/completions", json=payload, timeout=timeout)
        self._raise_for_status(response)
        return self._parse_response(response.json(), request_id)

    def count_tokens(self, text: str) -> int:
        """Count the tokens in a text using the server's /tokenize endpoint.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        payload = {"model": self._resolve_model(), "prompt": text}
        response = self._http.post("/tokenize", json=payload)
        self._raise_for_status(response)
        return int(response.json()["count"])


class _AsyncHttpInferClient(_ChatPayloadMixin):
    """Asyncio HTTP client for an OpenAI-compatible chat server.

    Counterpart of _HttpInferClient built on httpx.AsyncClient, with an additional streaming call.
    Supports use as an async context manager.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: Optional[str] = None,
        api_key: str = "EMPTY",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Create the HTTP client; see _HttpInferClient.__init__ for the arguments."""
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def __aenter__(self) -> "_AsyncHttpInferClient":
        """Return the client itself."""
        return self

    async def __aexit__(self, *_) -> None:
        """Close the client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def _resolve_model(self) -> str:
        """Return the model name, querying /v1/models once and caching the first entry if none was given."""
        if self._model is None:
            response = await self._http.get("/v1/models")
            self._raise_for_status(response)
            self._model = response.json()["data"][0]["id"]
        return self._model

    async def _chat(
        self,
        messages: list[Message],
        *,
        max_new_tokens: Optional[int],
        temperature: Optional[float],
        enable_thinking: Optional[bool],
        request_id: Optional[str],
        timeout: float,
    ) -> ChatInferResult:
        """Send a chat completion request and parse the reply.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        payload = self._build_payload(
            messages, model=await self._resolve_model(), max_new_tokens=max_new_tokens,
            temperature=temperature, enable_thinking=enable_thinking,
        )
        response = await self._http.post("/v1/chat/completions", json=payload, timeout=timeout)
        self._raise_for_status(response)
        return self._parse_response(response.json(), request_id)

    async def _chat_stream(
        self,
        messages: list[Message],
        *,
        max_new_tokens: Optional[int],
        temperature: Optional[float],
        enable_thinking: Optional[bool],
        timeout: float,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, yielding content deltas as they arrive.

        Reads the server-sent-event lines of a streaming request and yields each non-empty delta content
        string until '[DONE]'.

        Raises:
            RuntimeError: If the server returns a non-200 status or sends an error object mid-stream.
        """
        payload = self._build_payload(
            messages, model=await self._resolve_model(), max_new_tokens=max_new_tokens,
            temperature=temperature, enable_thinking=enable_thinking,
        )
        payload["stream"] = True
        async with self._http.stream("POST", "/v1/chat/completions", json=payload, timeout=timeout) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", "replace")
                raise RuntimeError(
                    f"infer_stream() failed: HTTP {response.status_code} from {response.request.url}: {body[:2000]}"
                )
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                parsed = json.loads(data)
                if "choices" not in parsed:
                    error = parsed.get("error")
                    message = error.get("message") if isinstance(error, dict) else parsed
                    raise RuntimeError(f"infer_stream() failed mid-stream: {message}")
                delta = parsed["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content

    async def count_tokens(self, text: str) -> int:
        """Count the tokens in a text using the server's /tokenize endpoint.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        payload = {"model": await self._resolve_model(), "prompt": text}
        response = await self._http.post("/tokenize", json=payload)
        self._raise_for_status(response)
        return int(response.json()["count"])


class AxLlmClient(_HttpInferClient):
    """Blocking client for a text-only LLM served through an OpenAI-compatible API."""

    def infer(
        self,
        prompt: Union[str, list[Message]],
        *,
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        request_id: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> ChatInferResult:
        """Run a chat completion and wait for the full answer.

        Args:
            prompt (Union[str, list[Message]]): A user prompt, or a ready-made list of chat messages (used as is,
                system_prompt is then ignored).
            system_prompt (Optional[str], optional): System message placed before the user prompt. Defaults to None.
            max_new_tokens (Optional[int], optional): Maximum tokens to generate; server default if None.
            temperature (Optional[float], optional): Sampling temperature; server default if None.
            enable_thinking (Optional[bool], optional): Passed as chat_template_kwargs.enable_thinking when not None.
            request_id (Optional[str], optional): Echoed in the result; not sent to the server.
            timeout (float, optional): Request timeout in seconds. Defaults to 60.0.

        Returns:
            ChatInferResult: The answer and usage details.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        messages = self._build_messages(prompt, system_prompt=system_prompt)
        return self._chat(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, request_id=request_id, timeout=timeout,
        )

    def _build_messages(
        self, prompt: Union[str, list[Message]], *, system_prompt: Optional[str] = None,
    ) -> list[Message]:
        """Build chat messages: a list prompt is returned unchanged; a string becomes a user message, preceded by a system message if given."""
        if isinstance(prompt, list):
            return prompt
        messages: list[Message] = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages


class AsyncAxLlmClient(_AsyncHttpInferClient):
    """Asyncio client for a text-only LLM served through an OpenAI-compatible API."""

    async def infer(
        self,
        prompt: Union[str, list[Message]],
        *,
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        request_id: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> ChatInferResult:
        """Run a chat completion and await the full answer; arguments, result and errors are as for AxLlmClient.infer."""
        messages = self._build_messages(prompt, system_prompt=system_prompt)
        return await self._chat(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, request_id=request_id, timeout=timeout,
        )

    def infer_stream(
        self,
        prompt: Union[str, list[Message]],
        *,
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> AsyncIterator[str]:
        """Stream a chat completion, yielding text chunks as they are generated.

        Arguments are as for infer(), without request_id. The request is sent when the iterator is first awaited.

        Returns:
            AsyncIterator[str]: Async iterator of content deltas.

        Raises:
            RuntimeError: While iterating, if the server returns a non-200 status or an error mid-stream.
        """
        messages = self._build_messages(prompt, system_prompt=system_prompt)
        return self._chat_stream(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, timeout=timeout,
        )

    def _build_messages(
        self, prompt: Union[str, list[Message]], *, system_prompt: Optional[str] = None,
    ) -> list[Message]:
        """Build chat messages; same as AxLlmClient._build_messages."""
        return AxLlmClient._build_messages(self, prompt, system_prompt=system_prompt)


class AxVlmClient(_HttpInferClient):
    """Blocking client for a vision-language model served through an OpenAI-compatible API.

    Images are sent as base64 data URLs in the user message, optionally resized first.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: Optional[str] = None,
        api_key: str = "EMPTY",
        timeout: float = _DEFAULT_TIMEOUT,
        image_resize: Optional[tuple[int, int]] = None,
    ) -> None:
        """Create the client.

        Args:
            base_url (str): Server base URL.
            model (Optional[str], optional): Model name; resolved from /v1/models if None.
            api_key (str, optional): Bearer token. Defaults to 'EMPTY'.
            timeout (float, optional): Default request timeout in seconds. Defaults to 60.0.
            image_resize (Optional[tuple[int, int]], optional): (width, height) every image is resized to before
                sending (aspect ratio not preserved); None sends images unchanged. Defaults to None.
        """
        super().__init__(base_url, model=model, api_key=api_key, timeout=timeout)
        self._image_resize = image_resize

    def infer(
        self,
        images: list[bytes],
        prompt: Optional[str] = None,
        *,
        image_mime_type: str = "image/jpeg",
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        request_id: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> ChatInferResult:
        """Run a chat completion over one or more images and wait for the full answer.

        Args:
            images (list[bytes]): Encoded images, added to the user message in order.
            prompt (Optional[str], optional): Text appended after the images. Defaults to None.
            image_mime_type (str, optional): MIME type declared for all images. Defaults to 'image/jpeg'.
            system_prompt (Optional[str], optional): System message placed first. Defaults to None.
            max_new_tokens (Optional[int], optional): Maximum tokens to generate; server default if None.
            temperature (Optional[float], optional): Sampling temperature; server default if None.
            enable_thinking (Optional[bool], optional): Passed as chat_template_kwargs.enable_thinking when not None.
            request_id (Optional[str], optional): Echoed in the result; not sent to the server.
            timeout (float, optional): Request timeout in seconds. Defaults to 60.0.

        Returns:
            ChatInferResult: The answer and usage details.

        Raises:
            RuntimeError: If the server returns a non-200 status.
        """
        messages = self._build_messages(
            images, prompt, image_mime_type=image_mime_type, system_prompt=system_prompt,
        )
        return self._chat(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, request_id=request_id, timeout=timeout,
        )

    def _build_messages(
        self,
        images: list[bytes],
        prompt: Optional[str],
        *,
        image_mime_type: str = "image/jpeg",
        system_prompt: Optional[str] = None,
    ) -> list[Message]:
        """Build chat messages with the images (resized if configured) as image_url parts followed by the optional text prompt."""
        if self._image_resize is not None:
            images = [_resize_image_bytes(img, self._image_resize, image_mime_type) for img in images]
        content: list[Message] = [
            {"type": "image_url", "image_url": {"url": self._image_bytes_to_data_url(img, image_mime_type)}}
            for img in images
        ]
        if prompt is not None:
            content.append({"type": "text", "text": prompt})
        messages: list[Message] = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        return messages


class AsyncAxVlmClient(_AsyncHttpInferClient):
    """Asyncio client for a vision-language model served through an OpenAI-compatible API; see AxVlmClient."""

    def __init__(
        self,
        base_url: str,
        *,
        model: Optional[str] = None,
        api_key: str = "EMPTY",
        timeout: float = _DEFAULT_TIMEOUT,
        image_resize: Optional[tuple[int, int]] = None,
    ) -> None:
        """Create the client; see AxVlmClient.__init__ for the arguments."""
        super().__init__(base_url, model=model, api_key=api_key, timeout=timeout)
        self._image_resize = image_resize

    async def infer(
        self,
        images: list[bytes],
        prompt: Optional[str] = None,
        *,
        image_mime_type: str = "image/jpeg",
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        request_id: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> ChatInferResult:
        """Run a chat completion over one or more images and await the answer; arguments, result and errors are as for AxVlmClient.infer."""
        messages = self._build_messages(
            images, prompt, image_mime_type=image_mime_type, system_prompt=system_prompt,
        )
        return await self._chat(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, request_id=request_id, timeout=timeout,
        )

    def infer_stream(
        self,
        images: list[bytes],
        prompt: Optional[str] = None,
        *,
        image_mime_type: str = "image/jpeg",
        system_prompt: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> AsyncIterator[str]:
        """Stream a chat completion over one or more images, yielding text chunks; arguments are as for AxVlmClient.infer without request_id. See AsyncAxLlmClient.infer_stream."""
        messages = self._build_messages(
            images, prompt, image_mime_type=image_mime_type, system_prompt=system_prompt,
        )
        return self._chat_stream(
            messages, max_new_tokens=max_new_tokens, temperature=temperature,
            enable_thinking=enable_thinking, timeout=timeout,
        )

    def _build_messages(
        self,
        images: list[bytes],
        prompt: Optional[str],
        *,
        image_mime_type: str = "image/jpeg",
        system_prompt: Optional[str] = None,
    ) -> list[Message]:
        """Build chat messages; same as AxVlmClient._build_messages."""
        return AxVlmClient._build_messages(
            self, images, prompt, image_mime_type=image_mime_type, system_prompt=system_prompt,
        )
