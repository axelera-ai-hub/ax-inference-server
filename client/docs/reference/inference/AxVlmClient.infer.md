# AxVlmClient.infer

## Summary
`infer` runs a chat completion over one or more images and waits for the full answer.

## Detailed Description
### Behavior
The client optionally resizes each image to `image_resize`. It encodes each as a base64 data URL and adds an `image_url` part per image in order. A text part with `prompt` follows if given. A system message goes first when `system_prompt` is set. The payload fields `max_tokens`, `temperature` and `chat_template_kwargs.enable_thinking` appear only when you pass them.

### Concurrency
Concurrency behavior depends on the underlying runtime.

### Constraints
All images in one call share `image_mime_type`. Resizing writes JPEG for unknown MIME types and PNG or WEBP for those types.

## Signature
```python
AxVlmClient.infer(
    images: list[bytes],
    prompt: Optional[str] = None,
    *,
    image_mime_type: str = "image/jpeg",
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
| `images` | `list[bytes]` | none | yes | Encoded images, added to the user message in order. |
| `prompt` | `Optional[str]` | `None` | no | Text appended after the images. |
| `image_mime_type` | `str` | `"image/jpeg"` | no | MIME type declared for all images. |
| `system_prompt` | `Optional[str]` | `None` | no | System message placed first. |
| `max_new_tokens` | `Optional[int]` | `None` | no | Maximum tokens to generate. |
| `temperature` | `Optional[float]` | `None` | no | Sampling temperature. |
| `enable_thinking` | `Optional[bool]` | `None` | no | Sent as `chat_template_kwargs.enable_thinking` when not `None`. |
| `request_id` | `Optional[str]` | `None` | no | Echoed in the result. The client does not send it. |
| `timeout` | `float` | `60.0` | no | Request timeout in seconds. |

## Returns
[ChatInferResult](ChatInferResult.md).

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | The server returns a non-200 status. | Fix the request or the server. |
| `httpx.TimeoutException` | The request exceeds `timeout`. | Raise `timeout`. |

## Usage Examples
### Basic
```python
from inference.llm_vlm import AxVlmClient

with AxVlmClient("http://localhost:8001", image_resize=(1024, 1024)) as vlm:
    result = vlm.infer([image_bytes], prompt="Describe this image.")
    print(result.answer)
```

## Edge Cases
- An empty `images` list sends a message with only the text part.
- Mixed MIME types need separate calls.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxVlmClient.infer](AsyncAxVlmClient.infer.md) | Async twin. |
| [AsyncAxVlmClient.infer_stream](AsyncAxVlmClient.infer_stream.md) | Streaming variant. |
| [AxLlmClient.infer](AxLlmClient.infer.md) | Text-only call. |

## Source Reference
`client/inference/llm_vlm.py::AxVlmClient.infer` (lines 478-516)
