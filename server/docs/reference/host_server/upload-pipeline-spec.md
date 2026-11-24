# `POST /api/v1/pipeline-spec`

## Summary

Stores a pipeline spec under `SDK_ROOT/pipeline_specs/<pipeline_id>/<filename>`.

## Detailed Description

### Behavior

- The handler parses `spec_content` as JSON and rejects invalid JSON.
- The handler creates `SDK_ROOT/pipeline_specs/<pipeline_id>/` if needed and writes the text unchanged.
- An existing file of the same name is overwritten.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The route takes no lock.

### Constraints

- `pipeline_id` must be 1 to 100 characters of letters, digits, `_` or `-`.
- `filename` must be a bare name that ends in `.json` and has no path separator.

## Signature

```http
POST /api/v1/pipeline-spec
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `pipeline_id` | `str` | none | Yes | Pipeline identifier. It names the directory. |
| `filename` | `str` | none | Yes | Bare `*.json` file name. |
| `spec_content` | `str` | none | Yes | JSON text of the spec. |

## Returns

`PipelineSpecUploadResponse`.

| Field | Type | Description |
|---|---|---|
| `saved_path` | `str` | Path of the stored spec on the host. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `spec_content` is not valid JSON. | Fix the JSON. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "demo", "filename": "spec.json", "spec_content": "{}"}' \
  "$BASE/api/v1/pipeline-spec"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "demo", "filename": "spec.json", "spec_content": "{}"}' \
  "$BASE/api/v1/pipeline-spec")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.saved_path' "$resp"
```

## Edge Cases

- The stored path is a valid `spec_path` for `POST /api/v1/pipelines/launch`.

## Related APIs

| API | Relationship |
|---|---|
| [pipeline-launch](./pipeline-launch.md) | Launches a pipeline from the stored spec. |
| [upload-yaml](./upload-yaml.md) | Stores YAML instead of JSON. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::upload_pipeline_spec` (lines 2536-2554)
- `deployment/host_server.py::PipelineSpecUploadRequest` (lines 2495-2523)
- `deployment/host_server.py::PipelineSpecUploadResponse` (lines 2526-2533)
