# `GET /api/v1/vllm/artifacts`

## Summary

Lists the compiled vLLM artifacts under `SDK_ROOT/build`.

## Detailed Description

### Behavior

- An artifact is a directory `SDK_ROOT/build/<name>/` that contains an `axscript` directory. The list is sorted by name.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the file system.

## Signature

```http
GET /api/v1/vllm/artifacts
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`VllmArtifactsResponse`.

| Field | Type | Description |
|---|---|---|
| `artifacts` | `list[VllmArtifactInfo]` | Each entry has `name` and `artifact_path` (`${SDK_ROOT}/build/<name>/axscript`, with a literal `${SDK_ROOT}`). |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/vllm/artifacts"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/vllm/artifacts")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.artifacts[].name' "$resp"
```

## Edge Cases

- A missing `build/` directory gives an empty list.

## Related APIs

| API | Relationship |
|---|---|
| [vllm-launch](./vllm-launch.md) | Takes an artifact path. |
| [list-models](./list-models.md) | Lists vision and VLM model directories. |
| [vLLM serving](../../vllm/serving.md) | Concept page for vLLM serving. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::list_vllm_artifacts` (lines 2866-2881)
- `deployment/host_server.py::VllmArtifactsResponse` (lines 2856-2863)
- `deployment/host_server.py::VllmArtifactInfo` (lines 2844-2853)
