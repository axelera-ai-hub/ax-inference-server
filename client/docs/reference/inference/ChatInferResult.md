# ChatInferResult

## Overview
`ChatInferResult` is a dataclass that holds one chat completion result. The `infer` methods of the LLM and VLM clients return it. Streaming calls yield text chunks instead. Import it from `inference.llm_vlm`.

## Attributes
| Attribute | Type | Description |
|---|---|---|
| `answer` | `str` | Text of the first choice's message. |
| `finish_reason` | `Optional[str]` | Why generation stopped, for example `stop` or `length`. |
| `prompt_tokens` | `Optional[int]` | Prompt token count from the usage block, if the server reports it. |
| `completion_tokens` | `Optional[int]` | Generated token count from the usage block, if reported. |
| `request_id` | `Optional[str]` | Id the caller passed to `infer`. The client does not send it to the server. |
| `raw` | `dict` | Full decoded JSON response. |

## Methods
| Method | Summary | Page |
|---|---|---|
| none | The class only holds fields. | none |

## Initialization
The clients create the object. All six fields are required positional or keyword arguments.

## Lifecycle
The object is a plain dataclass with no resources.

## Related Classes
| Class | Relationship |
|---|---|
| [AxLlmClient](AxLlmClient.md) | Returns it from `infer`. |
| [AxVlmClient](AxVlmClient.md) | Returns it from `infer`. |

## Source Reference
`client/inference/llm_vlm.py::ChatInferResult` (lines 21-39)
