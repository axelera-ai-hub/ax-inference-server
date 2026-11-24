# deploy.doc_id_for

## Summary

Derives a filesystem-safe name for a set of pipelines.

## Detailed Description

### Behavior

The function uses the first id. For N further ids it appends `_plus<N>`. It replaces every character outside `A-Za-z0-9_-` with `-` and cuts the result to 100 characters.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

`pipeline_ids` must not be empty.

## Signature

```python
def doc_id_for(pipeline_ids: list[str]) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| pipeline_ids | list[str] | none | Yes | Pipeline ids. The list must not be empty. |

## Returns

`str`. The name, at most 100 characters.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `IndexError` | `pipeline_ids` is empty. | Pass at least one id. |

## Usage Examples

### Basic

```python
from helper import deploy
print(deploy.doc_id_for(["iso-detect", "iso-detect-0"]))
# iso-detect_plus1
```

## Edge Cases

- `["a","b","c"]` gives `a_plus2`.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.compile_config](deploy.compile_config.md) | Uses the name for the default output directory. |

## Source Reference

- `client/examples/helper/deploy.py::doc_id_for` (lines 52-62)
