# `POST /api/v1/pipelines/cleanup-all`

## Summary

Stops every `axinferencenet_grpc` process on the host and every tracked vLLM instance.

## Detailed Description

### Behavior

- The handler scans `/proc` for processes whose name starts with the binary name and signals them. It sends SIGTERM, waits up to 10 s, then sends SIGKILL.
- The scan includes processes that this server did not launch.
- The handler clears the pipeline table and the vLLM table, and shuts down each tracked vLLM instance.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. Locks guard both process tables. The request blocks until the processes exit.

### Constraints

- The route needs no `SDK_ROOT`.
- Processes owned by other users are skipped.

## Signature

```http
POST /api/v1/pipelines/cleanup-all
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`PipelinesCleanupAllResponse`.

| Field | Type | Description |
|---|---|---|
| `killed_pids` | `list[int]` | Pids of `axinferencenet` processes found, including ones that exited on their own. |
| `killed_vllm_names` | `list[str]` | Sorted names of tracked vLLM instances that were shut down. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/pipelines/cleanup-all"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/pipelines/cleanup-all")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.' "$resp"
```

## Edge Cases

- Run this route before `POST /api/v1/devices/{device_id}/axdevice` on a busy host.
- `POST /api/v1/pipelines/shutdown` never touches vLLM instances. This route does.

## Related APIs

| API | Relationship |
|---|---|
| [pipeline-shutdown](./pipeline-shutdown.md) | Stops one pipeline. |
| [vllm-shutdown](./vllm-shutdown.md) | Stops one vLLM instance. |
| [device-axdevice](./device-axdevice.md) | Refuses to run while pipelines run. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::cleanup_all_pipelines` (lines 2813-2833)
- `deployment/host_server.py::PipelinesCleanupAllResponse` (lines 2801-2810)
