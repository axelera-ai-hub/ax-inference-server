# `GET /api/v1/devices/cpu_topology`

## Summary

Reports the host's NUMA nodes and CPU counts.

## Detailed Description

### Behavior

- With two or more NUMA nodes the handler reads each `cpulist` file under `/sys/devices/system/node`.
- With fewer than two nodes the response has `numa_available: false`, `os.cpu_count()` CPUs and an empty `nodes` list.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the file system.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/devices/cpu_topology
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`CpuTopologyResponse`.

| Field | Type | Description |
|---|---|---|
| `numa_available` | `bool` | True when the host has two or more NUMA nodes. |
| `total_cpus` | `int` | Logical CPUs on the host. |
| `nodes` | `list[NumaNodeCpuInfo]` | Each entry has `node`, `total_cpus` and `pinning_capacity`. `pinning_capacity` equals `total_cpus`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | A `cpulist` file cannot be read. | Check sysfs access. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/cpu_topology"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/devices/cpu_topology")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.nodes' "$resp"
```

## Edge Cases

- A host with fewer than two NUMA nodes returns `numa_available: false` and an empty `nodes` list.
- A node whose `cpulist` file cannot be read returns 500.

## Related APIs

| API | Relationship |
|---|---|
| [device-numa-plan](./device-numa-plan.md) | Plans CPU blocks per device. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_cpu_topology` (lines 2168-2182)
- `deployment/host_server.py::CpuTopologyResponse` (lines 2154-2165)
- `deployment/host_server.py::NumaNodeCpuInfo` (lines 2140-2151)
