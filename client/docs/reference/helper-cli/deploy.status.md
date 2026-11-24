# deploy.status

## Summary

Prints queue statistics for each pipeline and reports whether all are healthy.

## Detailed Description

### Behavior

For each pipeline, the function reads `GET /pipelines/<id>/queue-stats`. A stats line older than `STALE_S` (10.0) seconds counts as missing. It polls once a second for up to `wait_s` seconds. It prints one line per pipeline with `healthy`, `frames`, `dropped`, `avg_latency_ms`, `pending` and `stats_age_s`, or `no stats (<reason>)`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

A stats line older than `STALE_S` (10.0 seconds) counts as missing.

## Signature

```python
def status(ids: list[str], wait_s: float = 0.0) -> bool
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| ids | list[str] | none | Yes | Pipeline ids. |
| wait_s | float | 0.0 | No | Seconds to wait for fresh stats per pipeline. |

## Returns

`bool`. `True` when every pipeline has fresh stats and reports healthy.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The environment is unset. | Export both variables. |

## Usage Examples

### Basic

```python
from helper import deploy
ok = deploy.status(["iso-detect"], wait_s=30)
```

## Edge Cases

- Request failures turn into a `no stats` line and a `False` result.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.pipeline_ids](deploy.pipeline_ids.md) | Resolves the ids. |
| [cli-status](cli-status.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/deploy.py::status` (lines 191-226)
