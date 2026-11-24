# `POST /api/v1/prebuilt-models/download`

## Summary

Downloads a prebuilt model and generates its `.axnet` file under `SDK_ROOT/build/<name>/`.

## Detailed Description

### Behavior

- With `artifacts_only` the handler runs `axdownloadmodel <name>` and returns. It makes no `.axnet`.
- Otherwise an existing `.axnet` is returned as is unless `force` is set.
- If the `.axnet` is missing, the handler downloads the model first.
- The handler then regenerates the `.axnet` on a device and checks it with `axnet.smoke_test`.
- On a regenerate or smoke test failure the handler deletes the `.axnet` and returns 500.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. Two non-blocking locks apply. The download lock allows one download or provision. The provision step also takes the health check lock.

### Constraints

- `name` must be 1 to 100 characters of letters, digits, `_`, `.` or `-`.
- `aipu_cores` must be 1 to 4.
- The provision step needs the test image `client/assets/test_images/traffic_frame_480p.jpg`.

## Signature

```http
POST /api/v1/prebuilt-models/download
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `str` | none | Yes | Model name. |
| `version` | `str` or null | null | No | Model version passed to `axdownloadmodel`. |
| `opencl` | `bool` | `true` | No | Generate the `.axnet` with OpenCL enabled. |
| `device` | `int` or null | null | No | Device for provisioning. Null picks the lowest index. |
| `aipu_cores` | `int` | 4 | No | AIPU cores to compile for (1 to 4). |
| `force` | `bool` | `false` | No | Regenerate the `.axnet` even if it exists. |
| `artifacts_only` | `bool` | `false` | No | Download the artifacts only. Skip `.axnet` generation. |

## Returns

`PrebuiltModelDownloadResponse`.

| Field | Type | Description |
|---|---|---|
| `axnet_path` | `str` or null | Path of the `.axnet` with a literal `${SDK_ROOT}` prefix. Null with `artifacts_only`. |
| `already_present` | `bool` | Whether the `.axnet` existed before provisioning. With `artifacts_only` it reports the state after the download. |
| `regenerated` | `bool` | Whether this call generated the `.axnet`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 404 | `device` is not a known device index. | Use an index from `GET /api/v1/devices`. |
| 409 | Another download or provision runs, or a health check runs. | Retry after it finishes. |
| 500 | A tool or the test image is missing, a download fails, no device exists, or regeneration or the smoke test fails. | Read the detail and fix the cause. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "yolov8s-coco-onnx", "aipu_cores": 4}' \
  "$BASE/api/v1/prebuilt-models/download"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "yolov8s-coco-onnx", "aipu_cores": 4}' \
  "$BASE/api/v1/prebuilt-models/download")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.axnet_path' "$resp"
```

## Edge Cases

- A failed regeneration with `force` deletes the existing `.axnet`.
- The route blocks until the download and provisioning finish.

## Related APIs

| API | Relationship |
|---|---|
| [list-prebuilt-models](./list-prebuilt-models.md) | Lists downloadable names. |
| [patch-model-meta-key](./patch-model-meta-key.md) | Rewrites the meta key after provisioning. |
| [get-model-meta-key](./get-model-meta-key.md) | Reads the meta key from the model zoo. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::download_prebuilt_model` (lines 2316-2437)
- `deployment/host_server.py::PrebuiltModelDownloadRequest` (lines 2238-2273)
- `deployment/host_server.py::PrebuiltModelDownloadResponse` (lines 2276-2287)
