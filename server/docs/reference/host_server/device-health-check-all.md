# `POST /api/v1/devices/health/all`

## Summary

Runs a health check on every device and waits for the result.

## Detailed Description

### Behavior

- The route differs from `POST /api/v1/devices/health` in its inputs. It takes query parameters and sets one model for all devices.
- Each device gets up to two `axrunmodel` attempts, 3 s apart. A run executes `axrunmodel -d<index> ... --seconds 3 <artifact>`.
- The default model is `yolox-m-coco-onnx` version `1.8.0`. The handler downloads `<name>.axm` with `axdownloadmodel --axm` into `HEALTH_CHECK_MODEL_DIR` if absent.
- A model value that contains `/` or ends in `.axnet` or `.json` is a local path. The handler resolves it to the model JSON named by the `model=` line of the `.axnet`.
- Devices run in parallel, one thread per device. A model that cannot be resolved gives that device `healthy: false` and `attempts: 0`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A non-blocking lock serializes health checks and throughput tests. A second call returns 409 at once.

### Constraints

- `HEALTH_CHECK_MODEL_DIR` defaults to `/tmp/host_server_device_health_check`.
- `per_device_timeout_s` must be 1 to 600.

## Signature

```http
POST /api/v1/devices/health/all
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Query

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `per_device_timeout_s` | `int` | 20 | No | Seconds allowed for each `axrunmodel` run (1 to 600). |
| `model` | `str` | null | No | Model name or local path. Null selects the default model. |
| `model_version` | `str` | null | No | Version of the default model. The handler ignores it when `model` is set. |

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
| 400 | `per_device_timeout_s` is outside 1 to 600. | Use a value from 1 to 600. |
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
  "$BASE/api/v1/devices/health/all?per_device_timeout_s=30"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/health/all?per_device_timeout_s=30")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.devices[] | {index, healthy}' "$resp"
```

## Edge Cases

- The call blocks for the full check.
- `model_version` takes effect only when `model` is omitted. `POST /api/v1/devices/throughput` applies it with `model`.

## Related APIs

| API | Relationship |
|---|---|
| [device-health-check](./device-health-check.md) | Checks listed devices from a JSON body. |
| [device-health-check-one](./device-health-check-one.md) | Checks one device. |
| [device-health-check-async-start](./device-health-check-async-start.md) | Runs the same check in the background. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::check_all_devices_health` (lines 1731-1746)
- `deployment/host_server.py::DevicesHealthResponse` (lines 1388-1399)
