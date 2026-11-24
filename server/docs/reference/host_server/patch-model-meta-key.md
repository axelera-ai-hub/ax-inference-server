# `POST /api/v1/prebuilt-models/patch-meta-key`

## Summary

Rewrites the `meta_key` values in a provisioned model's `.axnet` file in place.

## Detailed Description

### Behavior

- The handler finds `SDK_ROOT/build/<name>/<name>.axnet`.
- The handler rewrites the `meta_key` values in the `.axnet` file in place.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The route takes no lock.

## Signature

```http
POST /api/v1/prebuilt-models/patch-meta-key
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `str` | none | Yes | Model name. |
| `meta_key` | `str` | none | Yes | New meta key. |

## Returns

`AxnetMetaKeyPatchResponse`.

| Field | Type | Description |
|---|---|---|
| `axnet_path` | `str` | Path of the `.axnet` with a literal `${SDK_ROOT}` prefix. |
| `patched` | `bool` | True if the file was modified. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 404 | The model's `.axnet` does not exist. | Provision it with `POST /api/v1/prebuilt-models/download`. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "yolov8s-coco-onnx", "meta_key": "yolov8s"}' \
  "$BASE/api/v1/prebuilt-models/patch-meta-key"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "yolov8s-coco-onnx", "meta_key": "yolov8s"}' \
  "$BASE/api/v1/prebuilt-models/patch-meta-key")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.patched' "$resp"
```

## Edge Cases

- The request model has no validator for `name`. The handler uses it as a path component.

## Related APIs

| API | Relationship |
|---|---|
| [get-model-meta-key](./get-model-meta-key.md) | Looks up the meta key to apply. |
| [download-prebuilt-model](./download-prebuilt-model.md) | Creates the `.axnet`. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::patch_axnet_meta_key` (lines 2464-2492)
- `deployment/host_server.py::AxnetMetaKeyPatchRequest` (lines 2440-2449)
- `deployment/host_server.py::AxnetMetaKeyPatchResponse` (lines 2452-2461)
