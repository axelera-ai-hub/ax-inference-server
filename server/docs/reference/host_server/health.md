# `GET /api/v1/health`

## Summary

Reports that the host server process is alive.

## Detailed Description

### Behavior

- Returns a fixed JSON body. The handler reads no configuration and touches no device.
- This is the only route that needs no `X-API-Key`.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler holds no state.

## Signature

```http
GET /api/v1/health
(no authentication)
```

## Returns

JSON object.

| Field | Type | Description |
|---|---|---|
| `status` | `str` | Always `"ok"`. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 200 | The server is running. | None. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  "$BASE/api/v1/health"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  "$BASE/api/v1/health")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.status' "$resp"
```

## Edge Cases

- The route does not check `SDK_ROOT`, the SDK tools or the devices. A 200 response proves only that uvicorn serves requests.

## Related APIs

| API | Relationship |
|---|---|
| [authentication](./authentication.md) | Every other route requires this authentication. |
| [server-restart](./server-restart.md) | Poll this route to see when the server is back. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::health` (lines 93-96)
