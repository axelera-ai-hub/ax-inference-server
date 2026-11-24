# `POST /api/v1/devices/health/all/start`

## Summary

Starts a background health check of all devices and returns at once.

## Detailed Description

### Behavior

- The handler counts the devices, resets the progress state and starts a daemon thread.
- The thread runs the same check as `POST /api/v1/devices/health/all`. It records progress for `GET /api/v1/devices/health/status`.
- If a background run is in progress, the handler starts nothing and returns `already_running: true` with the stored `total`.
- A failure inside the thread, such as a held lock, sets the `error` field of the status.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the progress state. The check runs on a daemon thread and shares the health check lock.

### Constraints

- `HEALTH_CHECK_MODEL_DIR` defaults to `/tmp/host_server_device_health_check`.
- `per_device_timeout_s` must be 1 to 600.

## Signature

```http
POST /api/v1/devices/health/all/start
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Query

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `per_device_timeout_s` | `int` | 20 | No | Seconds allowed for each `axrunmodel` run (1 to 600). |
| `model` | `str` | null | No | Model name or local path. Null selects the default model. |
| `model_version` | `str` | null | No | Version of the default model. The check ignores it when `model` is set. |

## Returns

`StartDevicesHealthResponse`.

| Field | Type | Description |
|---|---|---|
| `already_running` | `bool` | True if a background run was in progress. |
| `total` | `int` | Number of devices in the run. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `per_device_timeout_s` is outside 1 to 600. | Use a value from 1 to 600. |
| 500 | `axdevice` is missing or fails. | Check the SDK venv. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/health/all/start"
```

### Production

```bash
BASE="http://<host>:8088"
curl -sS -X POST -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/devices/health/all/start"
while :; do
  s=$(curl -sS -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/devices/health/status")
  [ "$(echo "$s" | jq .done)" = "true" ] && break
  sleep 2
done
echo "$s" | jq '{healthy_count, total, error}'
```

## Edge Cases

- A synchronous health check or throughput test that holds the lock makes the background run record an error and finish.
- Progress state lives in memory. A server restart clears it.

## Related APIs

| API | Relationship |
|---|---|
| [device-health-check-async-status](./device-health-check-async-status.md) | Reads the progress. |
| [device-health-check-all](./device-health-check-all.md) | Runs the same check synchronously. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::start_all_devices_health` (lines 1788-1820)
- `deployment/host_server.py::StartDevicesHealthResponse` (lines 1776-1785)
