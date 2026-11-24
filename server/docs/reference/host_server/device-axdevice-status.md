# `GET /api/v1/devices/{device_id}/axdevice`

## Summary

Reports one device's `axdevice -v` line and its parsed power limit.

## Detailed Description

### Behavior

- The handler runs `axdevice -v` and picks the line `Device <device_id>: ...`.
- The handler parses `power-limit=<value>` from that line. The value is a float in watts or `off`.
- The route needs no `confirm` and does not check for running pipelines.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The route does not take the maintenance lock. It can run while a maintenance call runs.

### Constraints

- The handler does not check the exit code of `axdevice`.

## Signature

```http
GET /api/v1/devices/{device_id}/axdevice
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `device_id` | `int` | none | Yes | Device index as listed by `GET /api/v1/devices`. |

## Returns

`AxdeviceStatusResponse`.

| Field | Type | Description |
|---|---|---|
| `device_id` | `int` | The device queried. |
| `device` | `str` or null | Its stripped `axdevice -v` line. |
| `power_limit_w` | `float`, `"off"` or null | Power limit parsed from the line. Null if the line shows none. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 404 | The device is not listed. | Use an index from `GET /api/v1/devices`. |
| 500 | `axdevice` is missing in the SDK venv. | Check the SDK venv. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/0/axdevice"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/0/axdevice")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.power_limit_w' "$resp"
```

## Edge Cases

- A device that `axdevice -v` does not list returns 404.
- A non-zero exit code of `axdevice -v` does not raise an error. The route reads whatever the command printed.

## Related APIs

| API | Relationship |
|---|---|
| [device-axdevice](./device-axdevice.md) | Changes the power limit or refreshes the device. |
| [list-devices](./list-devices.md) | Lists all devices. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::axdevice_device_status` (lines 595-615)
- `deployment/host_server.py::AxdeviceStatusResponse` (lines 513-524)
