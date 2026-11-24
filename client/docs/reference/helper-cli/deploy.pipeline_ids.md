# deploy.pipeline_ids

## Summary

Resolves pipeline ids from an id string or a compiled directory.

## Detailed Description

### Behavior

If `ids` is set, the function splits it on commas and drops empty items. Otherwise it reads the ids from the manifest of `directory`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

The caller must give `directory` or `ids`.

## Signature

```python
def pipeline_ids(directory: str | None, ids: str | None) -> list[str]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str \| None | none | Yes | Compiled directory holding a manifest. |
| ids | str \| None | none | Yes | Comma-separated ids. Takes precedence over `directory`. |

## Returns

`list[str]`. The pipeline ids.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | Neither argument is given, or the manifest is missing. | Pass one of them. |

## Usage Examples

### Basic

```python
from helper import deploy
print(deploy.pipeline_ids(None, "a,b"))
# ['a', 'b']
```

## Edge Cases

- An `ids` value of only commas yields an empty list.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.down](deploy.down.md) | Consumes the ids. |
| [deploy.status](deploy.status.md) | Consumes the ids. |

## Source Reference

- `client/examples/helper/deploy.py::pipeline_ids` (lines 164-181)
