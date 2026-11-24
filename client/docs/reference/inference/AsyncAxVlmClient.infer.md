# AsyncAxVlmClient.infer

## Summary
`infer` awaits a chat completion over one or more images. It is the async twin of [AxVlmClient.infer](AxVlmClient.infer.md).

## Detailed Description
### Behavior
Parameters, return value and errors are the same as the blocking method. The method is a coroutine.

### Concurrency
Concurrency behavior depends on the underlying runtime.

## Signature
```python
async AsyncAxVlmClient.infer(
    images: list[bytes], prompt: Optional[str] = None, *,
    image_mime_type: str = "image/jpeg", system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None, temperature: Optional[float] = None,
    enable_thinking: Optional[bool] = None, request_id: Optional[str] = None,
    timeout: float = 60.0,
) -> ChatInferResult
```

## Parameters
Same as [AxVlmClient.infer](AxVlmClient.infer.md#parameters).

## Returns
[ChatInferResult](ChatInferResult.md).

## Exceptions
Same as the blocking method.

## Usage Examples
### Basic
```python
result = await vlm.infer([image_bytes], prompt="Describe this image.")
```

## Edge Cases
- None beyond the blocking method.

## Related APIs
| API | Relationship |
|---|---|
| [AxVlmClient.infer](AxVlmClient.infer.md) | Blocking twin. |
| [AsyncAxVlmClient.infer_stream](AsyncAxVlmClient.infer_stream.md) | Streaming variant. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxVlmClient.infer` (lines 558-578)
