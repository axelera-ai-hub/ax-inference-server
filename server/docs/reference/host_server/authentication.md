# Authentication (`require_api_key`)

## Summary

Checks the `X-API-Key` header against `DEPLOYMENT_API_KEY` on every protected route.

## Detailed Description

### Behavior

- `require_api_key` is a FastAPI dependency. Each protected route lists it in its `dependencies` argument.
- `API_KEY_HEADER` is `APIKeyHeader(name="X-API-Key", auto_error=False)`, so a missing header reaches the function as `None`.
- The function reads `DEPLOYMENT_API_KEY` from the process environment on every request. `load_dotenv()` fills the environment from `.env` at import time.
- The function compares the header with `secrets.compare_digest`.
- The function returns `None` on success. The route handler then runs.

### Concurrency

FastAPI runs the dependency for each request. The function keeps no state.

### Constraints

- The server must have `DEPLOYMENT_API_KEY` set. Otherwise every protected route returns 500.
- Clients must send the key in the header `X-API-Key`. The server accepts no other location.
- `GET /api/v1/health` is the only unprotected route.

## Signature

```http
X-API-Key: <DEPLOYMENT_API_KEY>
# sent on every request to /api/v1/* except GET /api/v1/health
```

The Signature block shows the header every client sends. The Python signature of the dependency is `def require_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)) -> None`.

## Parameters

### Header

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `X-API-Key` | `str` | none | Yes | Must equal `DEPLOYMENT_API_KEY` on the server. |

## Returns

`None`. The dependency returns nothing and raises `HTTPException` on failure.

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | The header is absent, empty or not equal to `DEPLOYMENT_API_KEY`. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is unset or empty. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/sdk-root"
```

### Production

```bash
BASE="http://<host>:8088"
status=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/sdk-root")
case "$status" in
  200) echo "key accepted" ;;
  401) echo "key rejected" >&2; exit 1 ;;
  500) echo "server has no DEPLOYMENT_API_KEY" >&2; exit 1 ;;
  *) echo "HTTP $status" >&2; exit 1 ;;
esac
```

## Edge Cases

- A route can still return its own 500 for a missing `SDK_ROOT` after the key passes.
- An empty `X-API-Key` header counts as missing.

## Related APIs

| API | Relationship |
|---|---|
| [health](./health.md) | Needs no key. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::require_api_key` (lines 71-87)
- `deployment/host_server.py::API_KEY_HEADER` (lines 60-60)
