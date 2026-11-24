# `POST /api/v1/monitor/workers/{device_index}/stop`

## Summary

Stops buffering for a device and discards its samples.

## Detailed Description

### Behavior

- The handler removes the worker from the table.
- The handler signals the shared recorder thread to stop when no workers remain.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A module lock guards the worker table.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
POST /api/v1/monitor/workers/{device_index}/stop
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_index` | `int` | none | Yes | Device whose worker to remove. |

## Returns

JSON object.

| Field | Type | Description |
|---|---|---|
| `stopped` | `bool` | Always `true` on success. |
| `device_index` | `int` | The device. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 404 | The device has no worker. | List workers with `GET /api/v1/monitor/workers`. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/stop"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/workers/0/stop")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.stopped' "$resp"
```

## Edge Cases

- A second stop for the same device returns 404.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-worker-start](./monitor-worker-start.md) | Creates the worker. |
| [monitor-workers-list](./monitor-workers-list.md) | Lists active workers. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::stop_monitor_worker` (lines 1266-1281)
