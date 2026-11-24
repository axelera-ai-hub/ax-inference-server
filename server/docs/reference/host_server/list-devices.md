# `GET /api/v1/devices`

## Summary

Lists the Metis devices on the host.

## Detailed Description

### Behavior

- The handler runs `axdevice -v` from `SDK_ROOT/<SDK_VENV>/bin` with `AXELERA_FRAMEWORK` set.
- The handler parses each line that starts with `Device <N>: <name>`.
- The result is cached per SDK root for 20 s. `POST /api/v1/devices/{device_id}/axdevice` clears the cache.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The cache is a plain dict without a lock.

### Constraints

- `SDK_VENV` defaults to `venv`.
- Every device reports `cores` equal to 4 (`CORES_PER_DEVICE`).

## Signature

```http
GET /api/v1/devices
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`DevicesResponse`.

| Field | Type | Description |
|---|---|---|
| `devices` | `list[DeviceInfo]` | Each entry has `index` (`int`), `name` (address printed by `axdevice`) and `cores` (`int`). |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 500 | `axdevice` is missing or exits with a non-zero code. | Check the SDK venv and the driver. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.devices[] | {index, name}' "$resp"
```

## Edge Cases

- A host with no devices returns an empty list.

## Related APIs

| API | Relationship |
|---|---|
| [device-axdevice-status](./device-axdevice-status.md) | Reads one device line and power limit. |
| [device-axdevice](./device-axdevice.md) | Refreshes or reconfigures a device. |
| [device-health-check](./device-health-check.md) | Checks the devices end to end. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::list_devices` (lines 422-439)
- `deployment/host_server.py::DevicesResponse` (lines 374-381)
- `deployment/host_server.py::DeviceInfo` (lines 360-371)
