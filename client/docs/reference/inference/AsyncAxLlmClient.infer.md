# AsyncAxLlmClient.infer

## Summary
`infer` awaits a chat completion for a text prompt. It is the async twin of [AxLlmClient.infer](AxLlmClient.infer.md).

## Detailed Description
### Behavior
Parameters, return value and errors are the same as the blocking method. The only difference is that the method is a coroutine.

### Concurrency
Run many calls with `asyncio.gather`. Concurrency behavior depends on the underlying runtime.

## Signature
```python
async AsyncAxLlmClient.infer(
    prompt: Union[str, list[Message]], *, system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None, temperature: Optional[float] = None,
    enable_thinking: Optional[bool] = None, request_id: Optional[str] = None,
    timeout: float = 60.0,
) -> ChatInferResult
```

## Parameters
Same as [AxLlmClient.infer](AxLlmClient.infer.md#parameters).

## Returns
[ChatInferResult](ChatInferResult.md).

## Exceptions
Same as the blocking method.

## Usage Examples
### Basic
```python
import asyncio
from inference.llm_vlm import AsyncAxLlmClient

async def main():
    async with AsyncAxLlmClient("http://localhost:8000") as llm:
        result = await llm.infer("What is 2+2?")
        print(result.answer)

asyncio.run(main())
```

## Edge Cases
- None beyond the blocking method.

## Related APIs
| API | Relationship |
|---|---|
| [AxLlmClient.infer](AxLlmClient.infer.md) | Blocking twin. |
| [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md) | Streaming variant. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxLlmClient.infer` (lines 399-415)
