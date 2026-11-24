# `GET /api/v1/sdk-root`

## Summary

Returns the SDK root directory configured on the host.

## Detailed Description

### Behavior

- The handler reads `SDK_ROOT` from the environment and checks that it is a directory.
- The response carries the value as a string.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler holds no state.

## Signature

```http
GET /api/v1/sdk-root
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`SdkRootResponse`.

| Field | Type | Description |
|---|---|---|
| `sdk_root` | `str` | Value of `SDK_ROOT` on the host. |

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
  "$BASE/api/v1/sdk-root"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/sdk-root")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.sdk_root' "$resp"
```

## Edge Cases

- Use this route to build absolute paths for `spec_path` in `POST /api/v1/pipelines/launch`.

## Related APIs

| API | Relationship |
|---|---|
| [pipeline-launch](./pipeline-launch.md) | Needs a `spec_path` under the SDK root. |
| [upload-pipeline-spec](./upload-pipeline-spec.md) | Writes under the SDK root. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_sdk_root` (lines 165-168)
- `deployment/host_server.py::SdkRootResponse` (lines 155-162)
