# `POST /api/v1/benchmark-media/fetch`

## Summary

Starts a background fetch of the benchmark media files.

## Detailed Description

### Behavior

- The handler checks for `axdownloadmedia` in the SDK venv and starts a daemon thread.
- The thread produces nine files in `client/assets/test_images`: `traffic`, `intersection` and `dancing` at 480p, 720p and 1080p.
- The thread skips files that exist. It downloads catalog files with `axdownloadmedia`, and downsamples some with `ffmpeg` (H.264, CRF 20, no audio).
- A failure on one file is recorded and the run continues.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A non-blocking lock allows one fetch at a time. The thread releases it when the run ends.

## Signature

```http
POST /api/v1/benchmark-media/fetch
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Returns

`BenchmarkMediaFetchStartResponse`.

| Field | Type | Description |
|---|---|---|
| `started` | `bool` | `true` when the fetch starts. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 409 | A fetch is already running. | Poll `GET /api/v1/benchmark-media/status`. |
| 500 | `axdownloadmedia` is missing in the SDK venv. | Check the SDK venv. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/benchmark-media/fetch"
```

### Production

```bash
BASE="http://<host>:8088"
curl -sS -X POST -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/benchmark-media/fetch"
while :; do
  s=$(curl -sS -H "X-API-Key: $DEPLOYMENT_API_KEY" "$BASE/api/v1/benchmark-media/status")
  [ "$(echo "$s" | jq .running)" = "false" ] && break
  sleep 5
done
echo "$s" | jq '{ok, total}'
```

## Edge Cases

- Downsampled files need `ffmpeg` on the host.

## Related APIs

| API | Relationship |
|---|---|
| [benchmark-media-status](./benchmark-media-status.md) | Reads the progress. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::fetch_benchmark_media` (lines 3283-3301)
- `deployment/host_server.py::BenchmarkMediaFetchStartResponse` (lines 3112-3119)
