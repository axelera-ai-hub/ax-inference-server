# AxLlmClient.count_tokens

## Summary
`count_tokens` returns the token count of a text from the server's `/tokenize` endpoint.

## Detailed Description
### Behavior
The method posts `{"model": <model>, "prompt": text}` to `/tokenize` and returns `int(response["count"])`. It resolves the model name first if needed. `AxVlmClient` inherits the same method.

### Concurrency
Concurrency behavior depends on the underlying runtime.

### Constraints
The server must expose `/tokenize`.

## Signature
```python
AxLlmClient.count_tokens(text: str) -> int
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `text` | `str` | none | yes | Text to tokenize. |

## Returns
`int`: the token count.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| `RuntimeError` | The server returns a non-200 status. | Check the server and the `/tokenize` route. |

## Usage Examples
### Basic
```python
from inference.llm_vlm import AxLlmClient

with AxLlmClient("http://localhost:8000") as llm:
    n = llm.count_tokens("Hello world")
```

## Edge Cases
- The method uses the default client timeout, not a per-call value.

## Related APIs
| API | Relationship |
|---|---|
| [AsyncAxLlmClient.count_tokens](AsyncAxLlmClient.count_tokens.md) | Async twin. |
| [AxVlmClient](AxVlmClient.md) | Inherits the method. |

## Source Reference
`client/inference/llm_vlm.py::AxLlmClient` (lines 345-393) (`AxVlmClient` inherits it)
