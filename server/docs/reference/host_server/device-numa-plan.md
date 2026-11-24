# `GET /api/v1/devices/numa_plan`

## Summary

Plans CPU pinning so each device gets its own block of CPUs on its NUMA node.

## Detailed Description

### Behavior

- With two or more NUMA nodes under `/sys/devices/system/node`, the handler reads each device's node from `/sys/bus/pci/devices/0000:<bus>:00.0/numa_node`.
- The bus comes from the device address `metis-<n>:<bus>:<n>`.
- Otherwise every device uses node 0 and the online CPUs.
- Within a node, devices take consecutive blocks of `cores_per_device` CPUs in request order.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the file system and runs `axdevice -v`.

### Constraints

- The plan assumes PCI domain `0000`.

## Signature

```http
GET /api/v1/devices/numa_plan
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Query

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `indices` | `str` | none | Yes | Comma-separated device indices. |
| `cores_per_device` | `int` | 4 | No | CPUs per device. |

## Returns

`NumaPlanResponse`.

| Field | Type | Description |
|---|---|---|
| `numa_available` | `bool` | True when the host has two or more NUMA nodes. |
| `cores_per_device` | `int` | CPUs assigned to each device. |
| `plan` | `list[NumaDevicePlan]` | One entry per requested device, in request order. Each has `index`, `metis_addr`, `numa_node` and `cpus`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `indices` is malformed or empty. | Send integers separated by commas. |
| 404 | A requested device is unknown. | Use indices from `GET /api/v1/devices`. |
| 409 | A node has too few CPUs for the requested devices. | Request fewer devices or lower `cores_per_device`. |
| 500 | The PCI address or a sysfs file cannot be read, or `axdevice` fails. | Check sysfs access and the SDK venv. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/numa_plan?indices=0,1"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/numa_plan?indices=0,1")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.plan' "$resp"
```

## Edge Cases

- Join `cpus` into a CPU list string such as `0-3` for `taskset_cpus` in `POST /api/v1/pipelines/launch`.

## Related APIs

| API | Relationship |
|---|---|
| [device-cpu-topology](./device-cpu-topology.md) | Reports the CPUs per node. |
| [pipeline-launch](./pipeline-launch.md) | Takes `taskset_cpus` and `membind`. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_devices_numa_plan` (lines 2061-2137)
- `deployment/host_server.py::NumaPlanResponse` (lines 2009-2020)
- `deployment/host_server.py::NumaDevicePlan` (lines 1993-2006)
