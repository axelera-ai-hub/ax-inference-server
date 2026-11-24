# `GET /api/v1/monitor/workers/{device_index}/samples`

## Summary

Returns buffered AxMonitor samples for a device.

## Detailed Description

### Behavior

- Selection precedence is `index`, then `all`, then `n`.
- With none of them the route returns the newest sample, or an empty list if the buffer is empty.
- Lists are in oldest-first order.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler holds the buffer lock while it copies the selection.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/monitor/workers/{device_index}/samples
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_index` | `int` | none | Yes | Device with an active worker. |

### Query

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `n` | `int` | null | No | Return the most recent `n` samples. `0` returns none. |
| `all` | `bool` | `false` | No | Return the whole buffer. |
| `index` | `int` | null | No | Return the one sample `index` places back from the newest. `0` is the newest. |

## Returns

JSON object.

| Field | Type | Description |
|---|---|---|
| `device_index` | `int` | The device. |
| `interval_s` | `float` | Interval of the worker. |
| `total_samples` | `int` | Samples in the buffer. |
| `samples` | `list[object]` | Each entry has `timestamp` (Unix seconds) and `messages` (list of AxMonitor message dicts). |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 400 | `index` or `n` is negative. | Use a non-negative value. |
| 404 | The device has no worker, or `index` is at or beyond `total_samples`. | Start a worker or use a smaller `index`. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/samples?n=5"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/samples?n=5")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.samples | length' "$resp"
```

## Edge Cases

- `all` returns up to `MONITOR_WORKER_MAX_SAMPLES` samples, so the response can be large.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-worker-start](./monitor-worker-start.md) | Creates the worker. |
| [monitor-workers-list](./monitor-workers-list.md) | Shows the sample count. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_monitor_worker_samples` (lines 1304-1355)
