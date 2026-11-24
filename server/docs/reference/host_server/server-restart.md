# `POST /api/v1/server/restart`

## Summary

Restarts the host server process through a detached watchdog.

## Detailed Description

### Behavior

- The handler checks that `deployment/venv/bin/uvicorn` exists.
- The handler spawns a detached `bash` watchdog. The watchdog sleeps 8 s and then runs `uvicorn host_server:app` on `BIND_HOST` and `BIND_PORT`.
- The watchdog appends its output to `deployment/host_server_live.log`.
- A daemon thread calls `os._exit(0)` about 1.5 s after the response returns. The handler does not signal child processes.
- All in-memory state is lost: launched process tables, monitor buffers and progress state.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The exit runs on a separate daemon thread.

### Constraints

- `BIND_HOST` defaults to `0.0.0.0`. `BIND_PORT` defaults to `8088`.
- The route needs no `SDK_ROOT`.

## Signature

```http
POST /api/v1/server/restart
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`ServerRestartResponse`.

| Field | Type | Description |
|---|---|---|
| `scheduled` | `bool` | True once the watchdog is spawned. |
| `detail` | `str` | Host, port and timing of the relaunch. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 503 | The uvicorn binary is missing or the watchdog cannot be spawned. | Create `deployment/venv` with uvicorn or fix the OS error in the detail. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/server/restart"
```

### Production

```bash
BASE="http://<host>:8088"
curl -sS -X POST -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/server/restart"
until curl -sS -f "$BASE/api/v1/health" >/dev/null 2>&1; do sleep 2; done
echo "server is back"
```

## Edge Cases

- The server may still answer for about 1.5 s after the 200 response. Wait for health to fail, then succeed, to see the new process.
- The handler sends no signal to launched `axinferencenet_grpc` and vLLM processes. The new server starts with empty process tables.
- `POST /api/v1/pipelines/cleanup-all` finds `axinferencenet_grpc` processes by name. Whether the children survive the exit is inferred from code inspection, not stated in the code.

## Related APIs

| API | Relationship |
|---|---|
| [health](./health.md) | Poll to detect the restart. |
| [pipeline-cleanup-all](./pipeline-cleanup-all.md) | Stops processes the new server no longer tracks. |
| [monitor-restart](./monitor-restart.md) | Restarts `axsystemserver`, not the host server. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::restart_host_server` (lines 961-1006)
- `deployment/host_server.py::ServerRestartResponse` (lines 949-958)
