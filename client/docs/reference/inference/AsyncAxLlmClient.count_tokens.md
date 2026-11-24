# AsyncAxLlmClient.count_tokens

## Summary
`count_tokens` awaits the token count of a text. It is the async twin of [AxLlmClient.count_tokens](AxLlmClient.count_tokens.md).

## Detailed Description
### Behavior
Request, return value and errors are the same as the blocking method. The method is a coroutine. `AsyncAxVlmClient` inherits it.

### Concurrency
Concurrency behavior depends on the underlying runtime.

## Signature
```python
async AsyncAxLlmClient.count_tokens(text: str) -> int
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
| `RuntimeError` | The server returns a non-200 status. | Check the `/tokenize` route. |

## Usage Examples
### Basic
```python
n = await llm.count_tokens("Hello world")
```

## Edge Cases
- None beyond the blocking method.

## Related APIs
| API | Relationship |
|---|---|
| [AxLlmClient.count_tokens](AxLlmClient.count_tokens.md) | Blocking twin. |

## Source Reference
`client/inference/llm_vlm.py::AsyncAxLlmClient` (lines 396-447) (`AsyncAxVlmClient` inherits it)
