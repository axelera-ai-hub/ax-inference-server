# AxLlmClient

## Overview
`AxLlmClient` is the blocking client for a text-only LLM behind an OpenAI-compatible HTTP API. It uses a persistent `httpx.Client`. It fetches the model name from `/v1/models` on first use when you do not pass one. Import it with `from inference.llm_vlm import AxLlmClient`. The package `inference` does not re-export it. See [serving](../../../../server/docs/vllm/serving.md) and the [client concept page](../../client/client.md).

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `base_url` | `str` | Server base URL without a trailing slash. |

## Methods
| Method | Summary | Page |
|---|---|---|
| `__init__(base_url, *, model, api_key, timeout)` | Creates the HTTP client. | this page |
| `__enter__()` | Returns the client itself. | this page |
| `__exit__(*_)` | Calls `close()`. | this page |
| `close()` | Closes the underlying HTTP client. | this page |
| `infer(prompt, ...)` | Runs a chat completion and returns a `ChatInferResult`. | [AxLlmClient.infer](AxLlmClient.infer.md) |
| `count_tokens(text)` | Counts tokens with the server's `/tokenize` endpoint. | [AxLlmClient.count_tokens](AxLlmClient.count_tokens.md) |

## Initialization
```python
AxLlmClient(base_url: str, *, model: Optional[str] = None, api_key: str = "EMPTY", timeout: float = 60.0)
```

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `base_url` | `str` | none | yes | Server base URL. |
| `model` | `Optional[str]` | `None` | no | Model name. If `None`, the first model from `/v1/models` is used. |
| `api_key` | `str` | `"EMPTY"` | no | Bearer token for the `Authorization` header. |
| `timeout` | `float` | `60.0` | no | Default HTTP timeout in seconds. |

## Lifecycle
Create the client, call `infer`, then call `close()` or use a `with` block. The client resolves and caches the model name on the first request.

## Related Classes
| Class | Relationship |
|---|---|
| [AsyncAxLlmClient](AsyncAxLlmClient.md) | Asyncio twin with streaming. |
| [AxVlmClient](AxVlmClient.md) | Same transport with images. |
| [ChatInferResult](ChatInferResult.md) | Return type of `infer`. |

## Source Reference
`client/inference/llm_vlm.py::AxLlmClient` (lines 345-393)
