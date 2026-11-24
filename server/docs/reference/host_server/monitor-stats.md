# `GET /api/v1/monitor/stats`

## Summary

Returns one parsed AxMonitor snapshot for all devices.

## Detailed Description

### Behavior

- The handler runs `axmonitor --server-address <MONITOR_SERVER_ADDRESS> --ui console -c print` with a 5 s timeout.
- The binary is the last-sorting match of `/opt/axelera/runtime-*/bin/axmonitor`.
- The handler parses the text into per-device statistics. Each `# Device <N>: <name>` header starts a device.
- The result is cached for 1 s.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The cache is a module variable without a lock.

### Constraints

- `MONITOR_SERVER_ADDRESS` defaults to `127.0.0.1:5555`.
- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/monitor/stats
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`MonitorStatsResponse`.

| Field | Type | Description |
|---|---|---|
| `devices` | `dict[int, MonitorDeviceStats]` | Statistics keyed by device index. |
| `raw_output` | `str` | Combined stdout and stderr of the `axmonitor` run. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 503 | `axmonitor` is not installed, times out, or exits non-zero. | Run `setup.sh` with `--monitor`, or restart `axsystemserver` with `POST /api/v1/monitor/restart`. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/stats"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/stats")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.devices' "$resp"
```

## Edge Cases

- `MonitorDeviceStats` holds `device_name`, `power_limit_w`, `power_sensor_0_w`, `power_sensor_1_w`, `sys_core_utilization_pct`, `ai_cores`, `ddr_total_mb`, `ddr_used_mb` and `ddr_utilization_pct`. Fields the output lacks are null.
- `ai_cores` maps a core index to `core_utilization_pct`, `mvm_peak_utilization_pct` and `mvm_average_utilization_pct`.
- The handler computes `ddr_utilization_pct` as used over total DDR times 100.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-restart](./monitor-restart.md) | Restarts the service that this route reads. |
| [monitor-worker-start](./monitor-worker-start.md) | Buffers samples over time instead of one snapshot. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_monitor_stats` (lines 886-901)
- `deployment/host_server.py::MonitorStatsResponse` (lines 753-762)
- `deployment/host_server.py::MonitorDeviceStats` (lines 727-750)
- `deployment/host_server.py::MonitorCoreStats` (lines 713-724)
