# `GET /api/v1/models`

## Summary

Lists the compiled vision models and VLM artifact directories under the SDK root.

## Detailed Description

### Behavior

- A vision model is a directory `SDK_ROOT/build/<name>/` that holds `<name>.axnet`. The list is sorted by name.
- A VLM model is a directory that contains both a `vision/` and a `text/` subdirectory. The scan checks the SDK root, its children and its grandchildren.
- Path fields use a literal `${SDK_ROOT}` prefix.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the file system.

## Signature

```http
GET /api/v1/models
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`ModelsResponse`.

| Field | Type | Description |
|---|---|---|
| `vision_models` | `list[VisionModelInfo]` | Each entry has `name` and `axnet_path`. |
| `vlm_models` | `list[VlmModelInfo]` | Each entry has `name` (path relative to the SDK root, `.` for the root), `artifact_path`, `vision_subdir` (`vision`) and `text_subdir` (`text`). |

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
  "$BASE/api/v1/models"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/models")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.vision_models[].name' "$resp"
```

## Edge Cases

- A missing `build/` directory gives an empty `vision_models` list.
- A VLM directory found through two parents appears once.

## Related APIs

| API | Relationship |
|---|---|
| [list-prebuilt-models](./list-prebuilt-models.md) | Lists models that can be downloaded. |
| [download-prebuilt-model](./download-prebuilt-model.md) | Creates the `.axnet` that this route lists. |
| [vllm-artifacts](./vllm-artifacts.md) | Lists compiled vLLM artifacts. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::list_models` (lines 231-273)
- `deployment/host_server.py::ModelsResponse` (lines 219-228)
- `deployment/host_server.py::VisionModelInfo` (lines 191-200)
- `deployment/host_server.py::VlmModelInfo` (lines 203-216)
