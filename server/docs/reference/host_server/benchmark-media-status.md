# `GET /api/v1/benchmark-media/status`

## Summary

Reports the progress of the benchmark media fetch.

## Detailed Description

### Behavior

- The handler returns the in-memory progress of the last or current run.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler reads the progress dict without a lock.

### Constraints

- The route needs no `SDK_ROOT`.

## Signature

```http
GET /api/v1/benchmark-media/status
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`BenchmarkMediaStatusResponse`.

| Field | Type | Description |
|---|---|---|
| `running` | `bool` | Whether a fetch is in progress. |
| `current_file` | `str` or null | File being produced. |
| `stage` | `str` or null | `downloading`, `transferring` or `preprocessing`. |
| `results` | `list[BenchmarkMediaFetchResult]` | Each entry has `file`, `status` (`already_exists`, `downloaded`, `transcoded` or `error`) and `detail`. |
| `total` | `int` | Number of files in the plan (9). |
| `ok` | `bool` or null | Null until a run finishes. Then true if no file failed. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/benchmark-media/status"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/benchmark-media/status")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.' "$resp"
```

## Edge Cases

- Before the first run `results` is empty and `ok` is null.

## Related APIs

| API | Relationship |
|---|---|
| [benchmark-media-fetch](./benchmark-media-fetch.md) | Starts the fetch. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::benchmark_media_status` (lines 3304-3318)
- `deployment/host_server.py::BenchmarkMediaStatusResponse` (lines 3122-3139)
- `deployment/host_server.py::BenchmarkMediaFetchResult` (lines 3098-3109)
