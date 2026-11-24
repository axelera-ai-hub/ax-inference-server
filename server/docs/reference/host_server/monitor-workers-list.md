# `GET /api/v1/monitor/workers`

## Summary

Lists the active monitor workers.

## Detailed Description

### Behavior

- The handler returns one entry per worker with its interval, sample count, start time, last sample time and last error.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler locks the worker table, then each buffer in turn.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/monitor/workers
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

JSON object with one key.

| Field | Type | Description |
|---|---|---|
| `workers` | `list[object]` | One object per worker. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.workers' "$resp"
```

## Edge Cases

- Each worker object has `device_index`, `interval_s`, `sample_count`, `max_samples`, `started_at` (Unix seconds), `last_sample_at` (Unix seconds or null) and `last_error` (`str` or null).
- `last_error` is set when the recorder process exits. A stored sample clears it.
- An empty `workers` list means no worker runs.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-worker-start](./monitor-worker-start.md) | Creates a worker. |
| [monitor-worker-samples](./monitor-worker-samples.md) | Reads the samples of one worker. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::list_monitor_workers` (lines 1284-1301)
