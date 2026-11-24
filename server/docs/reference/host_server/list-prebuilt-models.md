# `GET /api/v1/prebuilt-models`

## Summary

Lists the models that `axdownloadmodel` can fetch.

## Detailed Description

### Behavior

- The handler runs `axdownloadmodel --list` in the SDK root and returns the non-empty output lines.
- The result is cached per SDK root for 600 s.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The cache is a plain dict without a lock.

## Signature

```http
GET /api/v1/prebuilt-models
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`PrebuiltModelsResponse`.

| Field | Type | Description |
|---|---|---|
| `models` | `list[str]` | Lines printed by `axdownloadmodel --list`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 500 | `axdownloadmodel` is missing or exits non-zero. | Check the SDK venv. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/prebuilt-models"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/prebuilt-models")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.models[]' "$resp"
```

## Edge Cases

- A model added upstream appears after the cache expires.

## Related APIs

| API | Relationship |
|---|---|
| [download-prebuilt-model](./download-prebuilt-model.md) | Downloads one of these models. |
| [list-models](./list-models.md) | Lists models already on the host. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::list_prebuilt_models` (lines 2200-2232)
- `deployment/host_server.py::PrebuiltModelsResponse` (lines 2185-2192)
