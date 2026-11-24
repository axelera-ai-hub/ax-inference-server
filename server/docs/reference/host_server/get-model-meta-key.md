# `GET /api/v1/models/{name}/meta-key`

## Summary

Looks up a model's meta key in the SDK model zoo.

## Detailed Description

### Behavior

- The handler scans every `*.yaml` under `SDK_ROOT/ax_models`.
- A file matches when a line starting at column 0 reads `name: <name>`.
- The meta key is the first stage name under the `pipeline:` key of the single matching file.
- The response gives the YAML path relative to the SDK root.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the file system.

## Signature

```http
GET /api/v1/models/{name}/meta-key
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `str` | none | Yes | Model name as declared in the YAML. |

## Returns

`ModelMetaKeyResponse`.

| Field | Type | Description |
|---|---|---|
| `meta_key` | `str` | Name of the first stage under `pipeline:`. |
| `source_yaml` | `str` | YAML path relative to the SDK root. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 404 | No YAML declares the name. | Check the model name. |
| 409 | Several YAMLs declare the name. | Remove the duplicate or use a unique name. |
| 422 | The YAML has no pipeline stage. | Fix the model YAML. |
| 500 | `SDK_ROOT/ax_models` does not exist. | Install the model zoo in the SDK. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/models/yolov8s-coco-onnx/meta-key"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/models/yolov8s-coco-onnx/meta-key")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.meta_key' "$resp"
```

## Edge Cases

- Unreadable YAML files are skipped.
- The `name:` value that the handler reads from a YAML can contain only letters, digits, `_`, `.` and `-`. Single or double quotes around it are optional.

## Related APIs

| API | Relationship |
|---|---|
| [patch-model-meta-key](./patch-model-meta-key.md) | Applies a meta key to a provisioned `.axnet`. |
| [download-prebuilt-model](./download-prebuilt-model.md) | Provisions the `.axnet`. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_model_meta_key` (lines 293-352)
- `deployment/host_server.py::ModelMetaKeyResponse` (lines 281-290)
