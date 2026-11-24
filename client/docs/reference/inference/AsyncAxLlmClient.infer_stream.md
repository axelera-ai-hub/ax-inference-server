# AsyncAxLlmClient.infer_stream

## Summary
`infer_stream` streams a chat completion and yields each text chunk as the server generates it.

## Detailed Description
### Behavior
The method builds the messages as `infer` does and returns an async iterator. The client sends the request when you first await the iterator. It sets `stream: true` and reads server-sent-event lines that start with `data: `. It stops at `[DONE]`. It yields each non-empty `delta.content` string. The method takes no `request_id`. `AsyncAxVlmClient.infer_stream` works the same with images.

### Concurrency
One iterator reads one HTTP response. Concurrency behavior depends on the underlying runtime.

### Constraints
The server must support `stream: true`. Only the async clients offer streaming.

## Signature
```python
AsyncAxLlmClient.infer_stream(
    prompt: Union[str, list[Message]],
    *,
    system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    enable_thinking: Optional[bool] = None,
    timeout: float = 60.0,
) -> AsyncIterator[str]
```

## Parameters
Same as [AxLlmClient.infer](AxLlmClient.infer.md#parameters), without `request_id`.

## Returns
`AsyncIterator[str]`: content deltas.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | While iterating, the server returns a non-200 status. | Fix the request or the server. |
| `RuntimeError` | The server sends an error object mid-stream (message `infer_stream() failed mid-stream: ...`). | Retry the request. |
| `json.JSONDecodeError` | A `data: ` line holds text that is not valid JSON. | Retry the request. |

## Usage Examples
### Basic
```python
import asyncio
from inference.llm_vlm import AsyncAxLlmClient

async def main():
    async with AsyncAxLlmClient("http://localhost:8000") as llm:
        async for chunk in llm.infer_stream("Tell a short story."):
            print(chunk, end="", flush=True)

asyncio.run(main())
```

## Edge Cases
- Lines that do not start with `data: ` are skipped.
- The stream yields no token counts. Use `infer` for usage figures.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxLlmClient.infer](AsyncAxLlmClient.infer.md) | Non-streaming variant. |
| [AsyncAxVlmClient.infer_stream](AsyncAxVlmClient.infer_stream.md) | Streaming with images. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxLlmClient.infer_stream` (lines 417-441)
