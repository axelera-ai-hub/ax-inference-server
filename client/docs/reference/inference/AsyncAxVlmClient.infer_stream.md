# AsyncAxVlmClient.infer_stream

## Summary
`infer_stream` streams a chat completion over one or more images and yields text chunks.

## Detailed Description
### Behavior
The method builds messages as [AxVlmClient.infer](AxVlmClient.infer.md) does. Streaming, errors and chunk handling are the same as in [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md). The method takes no `request_id`.

### Concurrency
Concurrency behavior depends on the underlying runtime.

## Signature
```python
AsyncAxVlmClient.infer_stream(
    images: list[bytes],
    prompt: Optional[str] = None,
    *,
    image_mime_type: str = "image/jpeg",
    system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    enable_thinking: Optional[bool] = None,
    timeout: float = 60.0,
) -> AsyncIterator[str]
```

## Parameters
Same as [AxVlmClient.infer](AxVlmClient.infer.md#parameters), without `request_id`.

## Returns
`AsyncIterator[str]`: content deltas.

## Exceptions
Same as [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md#exceptions).

## Usage Examples
### Basic
```python
async for chunk in vlm.infer_stream([image_bytes], prompt="Describe this image."):
    print(chunk, end="", flush=True)
```

## Edge Cases
- The stream yields no usage figures.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxVlmClient.infer](AsyncAxVlmClient.infer.md) | Non-streaming variant. |
| [AsyncAxLlmClient.infer_stream](AsyncAxLlmClient.infer_stream.md) | Text-only streaming. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxVlmClient.infer_stream` (lines 580-599)
