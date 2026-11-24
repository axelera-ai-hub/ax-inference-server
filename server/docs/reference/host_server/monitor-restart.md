# `POST /api/v1/monitor/restart`

## Summary

Restarts the `axsystemserver` service and clears the stats cache.

## Detailed Description

### Behavior

- The handler runs `service axsystemserver restart` with a 30 s timeout.
- The handler drops the cached stats snapshot before it checks the exit code.
- The response carries the combined stdout and stderr of the command.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The cache reset is a plain assignment without a lock.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
POST /api/v1/monitor/restart
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`MonitorRestartResponse`.

| Field | Type | Description |
|---|---|---|
| `restarted` | `bool` | True when the command succeeded. |
| `detail` | `str` | Output of the restart command. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 503 | The `service` command is missing, times out after 30 s, or exits non-zero. | Run `setup.sh` with `--monitor`, then retry. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/restart"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/monitor/restart")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.detail' "$resp"
```

## Edge Cases

- The stats cache is cleared even when the command exits non-zero.
- A timeout or a missing `service` command returns 503 without clearing the cache.

## Related APIs

| API | Relationship |
|---|---|
| [monitor-stats](./monitor-stats.md) | Reads statistics after the restart. |
| [server-restart](./server-restart.md) | Restarts the host server, not `axsystemserver`. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::restart_axsystemserver` (lines 916-946)
- `deployment/host_server.py::MonitorRestartResponse` (lines 904-913)
