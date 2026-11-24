# `POST /api/v1/devices/{device_id}/axdevice`

## Summary

Refreshes a device, reloads its firmware and/or sets its power limit through `axdevice`.

## Detailed Description

### Behavior

- The handler checks in this order: `confirm`, `action` or `power_limit_w`, the device, running pipelines, then the lock.
- `action: refresh` runs `axdevice -d <id> --refresh` (300 s limit). `action: reload_firmware` runs `axdevice -d <id> --reload-firmware` (300 s limit).
- `power_limit_w` runs `axdevice -d <id> --set-power-limit <value>` (60 s limit) after the action. The value is `off` or a number formatted with `%g`.
- The power step runs only if every earlier step exited with code 0.
- The response holds the device line before and after the steps. The handler clears the device list cache afterwards.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A non-blocking lock allows one maintenance call at a time. A second call returns 409 at once.

### Constraints

- `confirm` defaults to `false` and must be `true`.
- At least one of `action` and `power_limit_w` must be set.
- `power_limit_w` must be 0 to 500, or `off`.
- The server returns 409 while `axinferencenet_grpc` processes run, unless `allow_busy` is `true`.

## Signature

```http
POST /api/v1/devices/{device_id}/axdevice
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_id` | `int` | none | Yes | Device index as listed by `GET /api/v1/devices`. |

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `action` | `"refresh"`, `"reload_firmware"` or null | null | No | Operation to run first. |
| `power_limit_w` | `float`, `"off"` or null | null | No | Power limit in watts (0 to 500) or `off`. |
| `confirm` | `bool` | `false` | No | Must be `true`. A missing or false value returns 400. |
| `allow_busy` | `bool` | `false` | No | Proceed while `axinferencenet_grpc` processes run. |

## Returns

`AxdeviceResponse`.

| Field | Type | Description |
|---|---|---|
| `device_id` | `int` | The device targeted. |
| `ok` | `bool` | True if every step exited with code 0. |
| `steps` | `list[AxdeviceStepResult]` | Each step has `step`, `command`, `returncode`, `stdout`, `stderr` and `timed_out`. |
| `device_before` | `str` or null | The `axdevice -v` line before the steps. |
| `device_after` | `str` or null | The same line after the steps. |
| `power_limit_w_after` | `float`, `"off"` or null | Power limit parsed from `device_after`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `confirm` is not `true`. | Send `"confirm": true`. |
| 404 | The device is unknown. | Use an index from `GET /api/v1/devices`. |
| 409 | Pipelines run and `allow_busy` is false, or another maintenance call runs. | Call `POST /api/v1/pipelines/cleanup-all`, set `allow_busy`, or retry later. |
| 422 | Neither `action` nor `power_limit_w` is set, or `power_limit_w` is outside 0 to 500. | Fix the request to match the schema. |
| 500 | `axdevice` is missing, or `axdevice -v` fails. | Check the SDK venv. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "refresh", "power_limit_w": 400, "confirm": true}' \
  "$BASE/api/v1/devices/0/axdevice"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "refresh", "power_limit_w": 400, "confirm": true}' \
  "$BASE/api/v1/devices/0/axdevice")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.ok' "$resp"
```

## Edge Cases

- A step that exceeds its time limit reports `returncode: null`, `timed_out: true` and skips the power step.
- A device that rejects a power limit gives `ok: false`. The step `stderr` holds the `axdevice` error. The route does not check support beforehand.
- The action and the power limit run as two sequential `axdevice` commands. The power step needs every earlier step to exit with code 0.
- A refresh or firmware reload interrupts every user of the device.

## Related APIs

| API | Relationship |
|---|---|
| [device-axdevice-status](./device-axdevice-status.md) | Reads the device line without changing it. |
| [list-devices](./list-devices.md) | Lists the device indices. |
| [pipeline-cleanup-all](./pipeline-cleanup-all.md) | Stops running pipelines before maintenance. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::axdevice_device` (lines 618-684)
- `deployment/host_server.py::AxdeviceRequest` (lines 449-470)
- `deployment/host_server.py::AxdeviceResponse` (lines 493-510)
- `deployment/host_server.py::AxdeviceStepResult` (lines 473-490)
