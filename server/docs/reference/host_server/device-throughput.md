# `POST /api/v1/devices/throughput`

## Summary

Measures frame throughput on the listed devices and waits for the result.

## Detailed Description

### Behavior

- The handler resolves one model artifact. The default is `yolox-m-coco-onnx` version `1.8.0`.
- The handler runs `axrunmodel -d<index> ... --seconds <seconds> <artifact>` on every listed device in parallel.
- Each run has a timeout of `seconds` plus 60 s.
- `fps` is the sum of every `system:<value>` frame rate in the `axrunmodel` output.
- `aggregate_fps` sums `fps` over devices without an error.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The route shares the health check lock. A second health check or throughput test returns 409 at once.

### Constraints

- `device_indices` must be non-empty and non-negative.
- `seconds` must be 1 to 3600.

## Signature

```http
POST /api/v1/devices/throughput
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_indices` | `list[int]` | none | Yes | Devices to run on. |
| `seconds` | `int` | 30 | No | Run length per device (1 to 3600). |
| `model` | `str` or null | null | No | Model name or local path. Null selects the default model. |
| `model_version` | `str` or null | null | No | Version to download. Local paths ignore it. |

## Returns

`DevicesThroughputResponse`.

| Field | Type | Description |
|---|---|---|
| `devices` | `list[DeviceThroughput]` | Each entry has `index`, `fps` (0.0 on error) and `error`. |
| `aggregate_fps` | `float` | Sum of `fps` over successful devices. |
| `succeeded_count` | `int` | Devices without an error. |
| `total_count` | `int` | Devices measured. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | A device index is unknown, or a local model path is not found. | Use indices from `GET /api/v1/devices` and a valid path. |
| 409 | A health check or throughput test runs. | Retry after it finishes. |
| 500 | SDK tools are missing, the model download fails, or the local model files are broken. | Check the SDK venv and the model. |
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
  -d '{"device_indices": [0, 1], "seconds": 30}' \
  "$BASE/api/v1/devices/throughput"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"device_indices": [0, 1], "seconds": 30}' \
  "$BASE/api/v1/devices/throughput")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.aggregate_fps' "$resp"
```

## Edge Cases

- A model that cannot be resolved fails the whole request. The health check reports it per device instead.
- A failed run gives that device `fps: 0.0` and an `error`. The other devices still report.

## Related APIs

| API | Relationship |
|---|---|
| [device-health-check](./device-health-check.md) | Shares the same lock. |
| [list-devices](./list-devices.md) | Lists the device indices. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::run_devices_throughput` (lines 1979-1986)
- `deployment/host_server.py::DevicesThroughputRequest` (lines 1865-1896)
- `deployment/host_server.py::DevicesThroughputResponse` (lines 1849-1862)
- `deployment/host_server.py::DeviceThroughput` (lines 1835-1846)
