# `POST /api/v1/vllm/shutdown`

## Summary

Stops the vLLM instance that this server launched under a name.

## Detailed Description

### Behavior

- The handler removes the name from the vLLM table.
- The handler sends SIGTERM and then SIGKILL after 10 s.
- The response is 200 for an unknown name, with `stopped: false`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the vLLM table. The request blocks until the process exits.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
POST /api/v1/vllm/shutdown
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `str` | none | Yes | Name given at launch. |

## Returns

`VllmShutdownResponse`.

| Field | Type | Description |
|---|---|---|
| `stopped` | `bool` | False if no instance was tracked under that name. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "llm"}' \
  "$BASE/api/v1/vllm/shutdown"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "llm"}' \
  "$BASE/api/v1/vllm/shutdown")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.stopped' "$resp"
```

## Edge Cases

- An unknown name returns 200 with `stopped: false`.
- A process that ignores SIGTERM is killed with SIGKILL after 10 s.

## Related APIs

| API | Relationship |
|---|---|
| [vllm-launch](./vllm-launch.md) | Starts an instance. |
| [pipeline-cleanup-all](./pipeline-cleanup-all.md) | Stops every pipeline and vLLM instance. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::shutdown_vllm` (lines 3045-3055)
- `deployment/host_server.py::VllmShutdownRequest` (lines 3025-3032)
- `deployment/host_server.py::VllmShutdownResponse` (lines 3035-3042)
