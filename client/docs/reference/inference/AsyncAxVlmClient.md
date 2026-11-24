# AsyncAxVlmClient

## Overview
`AsyncAxVlmClient` is the asyncio twin of [AxVlmClient](AxVlmClient.md). It uses `httpx.AsyncClient`. Constructor arguments and payloads are identical. This page lists only the differences. Import it from `inference.llm_vlm`.

## Attributes
Same as `AxVlmClient`: `base_url`.

## Methods
| Method | Summary | Page |
|---|---|---|
| `__aenter__()` / `__aexit__(*_)` | Async context manager. `__aexit__` awaits `close()`. | this page |
| `close()` | Coroutine that closes the HTTP client. | this page |
| `infer(images, prompt, ...)` | Coroutine version of `infer`. | [AsyncAxVlmClient.infer](AsyncAxVlmClient.infer.md) |
| `infer_stream(images, prompt, ...)` | Yields text chunks. | [AsyncAxVlmClient.infer_stream](AsyncAxVlmClient.infer_stream.md) |
| `count_tokens(text)` | Coroutine version of `count_tokens`. | [AsyncAxLlmClient.count_tokens](AsyncAxLlmClient.count_tokens.md) |

## Initialization
Same as [AxVlmClient](AxVlmClient.md#initialization).

## Lifecycle
Use `async with AsyncAxVlmClient(...) as client`.

## Related Classes
| Class | Relationship |
|---|---|
| [AxVlmClient](AxVlmClient.md) | Blocking twin. |
| [AsyncAxLlmClient](AsyncAxLlmClient.md) | Text-only sibling. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxVlmClient` (lines 542-612)
