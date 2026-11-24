# `POST /api/v1/yaml`

## Summary

Stores an uploaded YAML file in `YAML_UPLOAD_DIR`.

## Detailed Description

### Behavior

- The handler takes the base name of the uploaded file name and ignores any directory part.
- The name must end in `.yaml` or `.yml`.
- The handler parses the content with `yaml.safe_load` and rejects invalid YAML.
- The handler creates `YAML_UPLOAD_DIR` if needed and overwrites a file of the same name.

### Concurrency

This handler is `async`. It reads the upload on the event loop and writes the file synchronously.

### Constraints

- `YAML_UPLOAD_DIR` defaults to `deployment/uploaded_yaml` and comes from the environment variable of the same name.
- The route does not need `SDK_ROOT`.

## Signature

```http
POST /api/v1/yaml
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `file` | `UploadFile` (multipart form field) | none | Yes | The YAML file. Its name must end in `.yaml` or `.yml`. |

## Returns

`YamlUploadResponse`.

| Field | Type | Description |
|---|---|---|
| `saved_path` | `str` | Path of the stored file on the host. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 400 | The name has the wrong extension or the content is not valid YAML. | Rename the file or fix the YAML. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS -X POST -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -F "file=@config.yaml" "$BASE/api/v1/yaml"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -F "file=@config.yaml" "$BASE/api/v1/yaml")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq -r .saved_path "$resp"
```

## Edge Cases

- A second upload with the same base name replaces the first file.
- The route stores the bytes unchanged. It does not rewrite the YAML.

## Related APIs

| API | Relationship |
|---|---|
| [upload-pipeline-spec](./upload-pipeline-spec.md) | Stores pipeline spec JSON instead of YAML. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::upload_yaml` (lines 109-137)
- `deployment/host_server.py::YamlUploadResponse` (lines 99-106)
- `deployment/host_server.py::YAML_UPLOAD_DIR` (lines 39-39)
