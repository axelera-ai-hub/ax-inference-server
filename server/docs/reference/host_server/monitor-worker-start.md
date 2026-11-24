# `POST /api/v1/monitor/workers/{device_index}/start`

## Summary

Starts buffering AxMonitor samples for a device, or updates the interval of an existing worker.

## Detailed Description

### Behavior

- The handler raises the interval to `MONITOR_WORKER_MIN_INTERVAL_S` when the request value is smaller.
- A device with a worker keeps it. The handler only updates its interval and returns `already_running: true`.
- A new worker creates an in-memory ring buffer of at most `MONITOR_WORKER_MAX_SAMPLES` samples.
- The first worker starts one shared recorder thread. The thread runs `axmonitor --record --export jsonl`, tails the file, and replaces the recorder every `MONITOR_RECORDER_ROTATE_S` seconds.
- The thread stores a record only when the buffer interval has elapsed since the previous stored record.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A module lock guards the worker table. Each buffer has its own lock.

### Constraints

- At most `MONITOR_WORKER_MAX_DEVICES` workers exist (default 30).
- `MONITOR_WORKER_MIN_INTERVAL_S` and `MONITOR_WORKER_DEFAULT_INTERVAL_S` default to 1.0.
- The route needs no `SDK_ROOT`.

## Signature

```http
POST /api/v1/monitor/workers/{device_index}/start
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_index` | `int` | none | Yes | Device to sample. Must be 0 or greater. |

### Query

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `interval_s` | `float` | `MONITOR_WORKER_DEFAULT_INTERVAL_S` | No | Seconds between stored samples. |

## Returns

`StartMonitorWorkerResponse`.

| Field | Type | Description |
|---|---|---|
| `already_running` | `bool` | True if the device already had a worker. |
| `device_index` | `int` | The device. |
| `interval_s` | `float` | Interval now in effect. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 400 | `device_index` is negative, or the worker cap is reached. | Use a non-negative index or stop an unused worker. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/start?interval_s=2"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/start?interval_s=2")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.interval_s' "$resp"
```

## Edge Cases

- The recorder thread raises 503 inside the thread when `axmonitor` is missing. The thread ends, the route still returns 200, and no samples arrive. Behavior inferred from code inspection.
- The buffer holds samples for any device that the recorder reports. The route does not check that the device exists.
- A server restart discards all workers and samples.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-worker-stop](./monitor-worker-stop.md) | Removes the worker. |
| [monitor-workers-list](./monitor-workers-list.md) | Lists workers and their sample counts. |
| [monitor-worker-samples](./monitor-worker-samples.md) | Reads the buffered samples. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::start_monitor_worker` (lines 1225-1263)
- `deployment/host_server.py::StartMonitorWorkerResponse` (lines 1211-1222)
- `deployment/host_server.py::MONITOR_WORKER_MAX_DEVICES` (lines 1010-1010)
- `deployment/host_server.py::MONITOR_WORKER_MAX_SAMPLES` (lines 1011-1011)
- `deployment/host_server.py::MONITOR_WORKER_MIN_INTERVAL_S` (lines 1012-1012)
- `deployment/host_server.py::MONITOR_WORKER_DEFAULT_INTERVAL_S` (lines 1013-1013)
- `deployment/host_server.py::MONITOR_RECORDER_ROTATE_S` (lines 1014-1014)
