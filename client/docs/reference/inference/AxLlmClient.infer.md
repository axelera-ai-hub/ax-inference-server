# AxLlmClient.infer

## Summary
`infer` runs a chat completion for a text prompt and waits for the full answer.

## Detailed Description
### Behavior
A string prompt becomes a user message. If `system_prompt` is set, a system message precedes it. A list prompt is used as given and `system_prompt` is ignored. The client posts to `/v1/chat/completions`. The payload includes `max_tokens`, `temperature` and `chat_template_kwargs.enable_thinking` only when you pass a value.

### Concurrency
Concurrency behavior depends on the underlying runtime.

### Constraints
The server must answer with HTTP 200.

## Signature
```python
AxLlmClient.infer(
    prompt: Union[str, list[Message]],
    *,
    system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    enable_thinking: Optional[bool] = None,
    request_id: Optional[str] = None,
    timeout: float = 60.0,
) -> ChatInferResult
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `prompt` | `Union[str, list[Message]]` | none | yes | A user prompt or a ready-made list of chat messages. |
| `system_prompt` | `Optional[str]` | `None` | no | System message placed before the user prompt. Ignored for a list prompt. |
| `max_new_tokens` | `Optional[int]` | `None` | no | Maximum tokens to generate. The server default applies if `None`. |
| `temperature` | `Optional[float]` | `None` | no | Sampling temperature. The server default applies if `None`. |
| `enable_thinking` | `Optional[bool]` | `None` | no | Sent as `chat_template_kwargs.enable_thinking` when not `None`. |
| `request_id` | `Optional[str]` | `None` | no | Echoed in the result. The client does not send it. |
| `timeout` | `float` | `60.0` | no | Request timeout in seconds. |

## Returns
[ChatInferResult](ChatInferResult.md) with the answer and usage details.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | The server returns a non-200 status. The message has the status, URL and the first 2000 body characters. | Fix the request or the server. |
| `httpx.TimeoutException` | The request exceeds `timeout`. | Raise `timeout`. |

## Usage Examples
### Basic
```python
from inference.llm_vlm import AxLlmClient

with AxLlmClient("http://localhost:8000") as llm:
    result = llm.infer("What is 2+2?", max_new_tokens=32)
    print(result.answer)
```

## Edge Cases
- `answer` is the first choice only.
- The `httpx` timeout exception is raised by `httpx`, not wrapped.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxLlmClient.infer](AsyncAxLlmClient.infer.md) | Async twin. |
| [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md) | Streaming variant. |
| [AxLlmClient.count_tokens](AxLlmClient.count_tokens.md) | Token counting. |

## Source Reference
`client/inference/llm_vlm.py::AxLlmClient.infer` (lines 348-381)
