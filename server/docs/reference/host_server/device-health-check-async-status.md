# `GET /api/v1/devices/health/status`

## Summary

Returns the progress of the background health check.

## Detailed Description

### Behavior

- The handler returns a copy of the progress state, taken under its lock.
- Before the first background run the state shows `running: false` and `done: false`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the copy.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/devices/health/status
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

JSON object.

| Field | Type | Description |
|---|---|---|
| `running` | `bool` | True while the check runs. |
| `total` | `int` | Number of devices in the run. |
| `completed` | `int` | Devices finished. |
| `current_indices` | `list[int]` | Devices being checked now. |
| `devices` | `list[object]` | Finished `DeviceHealth` results. |
| `healthy_count` | `int` | Healthy devices so far. |
| `done` | `bool` | True once the run ended. |
| `error` | `str` or null | Failure message, if the run failed. |

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
  "$BASE/api/v1/devices/health/status"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/health/status")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.' "$resp"
```

## Edge Cases

- `done: true` with a non-null `error` means the run failed before or during the check.

## Related APIs

| API | Relationship |
|---|---|
| [device-health-check-async-start](./device-health-check-async-start.md) | Starts the run. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_devices_health_status` (lines 1823-1826)
