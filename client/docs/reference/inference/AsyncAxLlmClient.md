# AsyncAxLlmClient

## Overview
`AsyncAxLlmClient` is the asyncio twin of [AxLlmClient](AxLlmClient.md). It uses `httpx.AsyncClient`. Constructor arguments, defaults and request payloads are identical. This page lists only the differences. Import it from `inference.llm_vlm`.

## Attributes
Same as `AxLlmClient`: `base_url`.

## Methods
| Method | Summary | Page |
|---|---|---|
| `__aenter__()` | Coroutine that returns the client itself. | this page |
| `__aexit__(*_)` | Coroutine that awaits `close()`. | this page |
| `close()` | Coroutine that closes the HTTP client. | this page |
| `infer(prompt, ...)` | Coroutine version of `infer`. | [AsyncAxLlmClient.infer](AsyncAxLlmClient.infer.md) |
| `infer_stream(prompt, ...)` | Yields text chunks as they are generated. | [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md) |
| `count_tokens(text)` | Coroutine version of `count_tokens`. | [AsyncAxLlmClient.count_tokens](AsyncAxLlmClient.count_tokens.md) |

## Initialization
Same as [AxLlmClient](AxLlmClient.md#initialization).

## Lifecycle
Use `async with AsyncAxLlmClient(...) as client`, or `await client.close()`.

## Related Classes
| Class | Relationship |
|---|---|
| [AxLlmClient](AxLlmClient.md) | Blocking twin. |
| [AsyncAxVlmClient](AsyncAxVlmClient.md) | Same transport with images. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxLlmClient` (lines 396-447)
