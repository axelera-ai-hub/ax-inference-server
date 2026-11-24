# server.log

## Summary

Prints a timestamped progress message to stderr.

## Detailed Description

### Behavior

The function prints `[HH:MM:SS] <msg>` to stderr and flushes.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Behavior inferred from code inspection.

## Signature

```python
def log(msg: str) -> None
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| msg | str | none | Yes | Message text. |

## Returns

`None`.

## Exceptions

None.

## Usage Examples

### Basic

```python
from helper import server
server.log("hello")
```

## Edge Cases

- Stdout stays free for command results.

## Related APIs

| API | Relationship |
|---|---|
| [server.api](server.api.md) | Callers of `log` report progress. |

## Source Reference

- `client/examples/helper/server.py::log` (lines 30-32)
