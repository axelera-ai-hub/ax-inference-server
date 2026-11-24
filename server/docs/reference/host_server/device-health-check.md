# `POST /api/v1/devices/health`

## Summary

Runs a health check on the listed devices, or on all devices, and waits for the result.

## Detailed Description

### Behavior

- The handler checks the devices named in `device_indices`. With none it checks every device that `axdevice -v` lists.
- Each device gets up to two `axrunmodel` attempts, 3 s apart. A run executes `axrunmodel -d<index> ... --seconds 3 <artifact>`.
- The default model is `yolox-m-coco-onnx` version `1.8.0`. The handler downloads `<name>.axm` with `axdownloadmodel --axm` into `HEALTH_CHECK_MODEL_DIR` if absent.
- A model value that contains `/` or ends in `.axnet` or `.json` is a local path. The handler resolves it to the model JSON named by the `model=` line of the `.axnet`.
- Devices run in parallel, one thread per device. A model that cannot be resolved gives that device `healthy: false` and `attempts: 0`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A non-blocking lock serializes health checks and throughput tests. A second call returns 409 at once.

### Constraints

- `HEALTH_CHECK_MODEL_DIR` defaults to `/tmp/host_server_device_health_check`.
- `per_device_timeout_s` must be 1 to 600.
- `device_indices` must hold non-negative integers.

## Signature

```http
POST /api/v1/devices/health
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_indices` | `list[int]` or null | null | No | Devices to check. Null means all. |
| `per_device_timeout_s` | `int` | 20 | No | Seconds allowed for each `axrunmodel` run (1 to 600). |
| `models` | `dict[int, str]` or null | null | No | Model per device index. Devices without an entry use the default model. |

## Returns

`DevicesHealthResponse`.

| Field | Type | Description |
|---|---|---|
| `devices` | `list[DeviceHealth]` | Each entry has `index`, `name`, `cores`, `healthy`, `attempts` (0 to 2) and `error` (null if healthy). |
| `healthy_count` | `int` | Number of healthy devices. |
| `total_count` | `int` | Number of devices checked. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `device_indices` names an unknown device. | Use indices from `GET /api/v1/devices`. |
| 409 | Another health check or throughput test runs. | Retry after it finishes. |
| 500 | `axdownloadmodel` or `axrunmodel` is missing in the SDK venv. | Check the SDK venv. |
| 500 | `axdevice` is missing, or `axdevice -v` fails. | Check the SDK venv. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"device_indices": [0, 1], "per_device_timeout_s": 30}' \
  "$BASE/api/v1/devices/health"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"device_indices": [0, 1], "per_device_timeout_s": 30}' \
  "$BASE/api/v1/devices/health")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.healthy_count' "$resp"
```

## Edge Cases

- The request body is optional. An empty request checks all devices with the default timeout.
- An empty `device_indices` list checks no device and returns `total_count: 0`.
- The call blocks for the full check. Use `POST /api/v1/devices/health/all/start` for a non-blocking check.

## Related APIs

| API | Relationship |
|---|---|
| [device-health-check-all](./device-health-check-all.md) | Checks all devices with query parameters. |
| [device-health-check-one](./device-health-check-one.md) | Checks one device. |
| [device-health-check-async-start](./device-health-check-async-start.md) | Starts a non-blocking check of all devices. |
| [device-throughput](./device-throughput.md) | Shares the same lock. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::check_devices_health` (lines 1722-1728)
- `deployment/host_server.py::DevicesHealthRequest` (lines 1402-1429)
- `deployment/host_server.py::DevicesHealthResponse` (lines 1388-1399)
- `deployment/host_server.py::DeviceHealth` (lines 1368-1385)
