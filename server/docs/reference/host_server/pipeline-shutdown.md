# `POST /api/v1/pipelines/shutdown`

## Summary

Stops the pipeline process that this server launched under a pipeline id.

## Detailed Description

### Behavior

- The handler removes the id from the process table.
- The handler sends SIGTERM and then SIGKILL after 10 s. It does nothing if the process already exited.
- The response is 200 for an unknown id, with `stopped: false`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the process table. The request blocks until the process exits.

### Constraints

- The route needs no `SDK_ROOT`.
- The route stops only processes that this server tracks.

## Signature

```http
POST /api/v1/pipelines/shutdown
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `pipeline_id` | `str` | none | Yes | Identifier given at launch. |

## Returns

`PipelineShutdownResponse`.

| Field | Type | Description |
|---|---|---|
| `stopped` | `bool` | False if no process was tracked under that id. |

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
  -d '{"pipeline_id": "demo"}' \
  "$BASE/api/v1/pipelines/shutdown"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "demo"}' \
  "$BASE/api/v1/pipelines/shutdown")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.stopped' "$resp"
```

## Edge Cases

- After a server restart the table is empty. Use `POST /api/v1/pipelines/cleanup-all` to stop the old processes.

## Related APIs

| API | Relationship |
|---|---|
| [pipeline-launch](./pipeline-launch.md) | Starts a pipeline. |
| [pipeline-cleanup-all](./pipeline-cleanup-all.md) | Stops every pipeline and vLLM instance. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::shutdown_pipeline` (lines 2788-2798)
- `deployment/host_server.py::PipelineShutdownRequest` (lines 2768-2775)
- `deployment/host_server.py::PipelineShutdownResponse` (lines 2778-2785)
