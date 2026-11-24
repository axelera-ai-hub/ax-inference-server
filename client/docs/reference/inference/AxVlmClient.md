# AxVlmClient

## Overview
`AxVlmClient` is the blocking client for a vision-language model behind an OpenAI-compatible HTTP API. It sends images as base64 data URLs in the user message. It can resize each image first. It lives in `client/inference/llm_vlm.py`, together with `AxLlmClient`. Import it with `from inference.llm_vlm import AxVlmClient`. See [serving](../../../../server/docs/vllm/serving.md) and the [client concept page](../../client/client.md).

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `base_url` | `str` | Server base URL without a trailing slash. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `__init__(base_url, *, model, api_key, timeout, image_resize)` | Creates the HTTP client. | this page |
| `__enter__()` / `__exit__(*_)` | Context manager that closes the client on exit. | this page |
| `close()` | Closes the underlying HTTP client. | this page |
| `infer(images, prompt, ...)` | Runs a chat completion over images. | [AxVlmClient.infer](AxVlmClient.infer.md) |
| `count_tokens(text)` | Counts tokens with `/tokenize`. | [AxLlmClient.count_tokens](AxLlmClient.count_tokens.md) |

## Initialization
```python
AxVlmClient(
    base_url: str, *, model: Optional[str] = None, api_key: str = "EMPTY",
    timeout: float = 60.0, image_resize: Optional[tuple[int, int]] = None,
)
```

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `base_url` | `str` | none | yes | Server base URL. |
| `model` | `Optional[str]` | `None` | no | Model name. Resolved from `/v1/models` if `None`. |
| `api_key` | `str` | `"EMPTY"` | no | Bearer token. |
| `timeout` | `float` | `60.0` | no | Default HTTP timeout in seconds. |
| `image_resize` | `Optional[tuple[int, int]]` | `None` | no | `(width, height)` for every image before sending. The aspect ratio is not preserved. |

## Lifecycle
Same as [AxLlmClient](AxLlmClient.md#lifecycle). Resizing uses Pillow and happens on each `infer` call.

## Related Classes
| Class | Relationship |
|---|---|
| [AsyncAxVlmClient](AsyncAxVlmClient.md) | Asyncio twin with streaming. |
| [AxLlmClient](AxLlmClient.md) | Text-only sibling. |
| [ChatInferResult](ChatInferResult.md) | Return type of `infer`. |

## Source Reference
`client/inference/llm_vlm.py::AxVlmClient` (lines 450-539)
