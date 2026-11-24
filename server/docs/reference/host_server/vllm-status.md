# `GET /api/v1/vllm/status`

## Summary

Lists the vLLM instances that this server launched and whether each still runs.

## Detailed Description

### Behavior

- The handler reads a snapshot of the vLLM table.
- `running` is true while the process has not exited.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the snapshot.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/vllm/status
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`VllmStatusResponse`.

| Field | Type | Description |
|---|---|---|
| `instances` | `list[VllmStatusInfo]` | Each entry has `name`, `pid`, `port`, `running` and `context_length`. |

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
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/vllm/status"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/vllm/status")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.instances' "$resp"
```

## Edge Cases

- The table is empty after a server restart, even if vLLM processes still run.

## Related APIs

| API | Relationship |
|---|---|
| [vllm-launch](./vllm-launch.md) | Adds an instance. |
| [vllm-shutdown](./vllm-shutdown.md) | Removes an instance. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::vllm_status` (lines 3086-3095)
- `deployment/host_server.py::VllmStatusResponse` (lines 3076-3083)
- `deployment/host_server.py::VllmStatusInfo` (lines 3058-3073)
