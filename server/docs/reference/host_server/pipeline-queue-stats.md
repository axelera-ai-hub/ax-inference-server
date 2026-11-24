# `GET /api/v1/pipelines/{pipeline_id}/queue-stats`

## Summary

Returns the latest queue statistics that a launched pipeline logged.

## Detailed Description

### Behavior

- The handler reads the last 64 KiB of `SDK_ROOT/pipeline_specs/<pipeline_id>/axinferencenet_uring.log`.
- The handler picks the last line of the form `[HH:MM:SS.ffffff] [STATS] STATS_JSON {...}`.
- The response copies the JSON payload and adds `stats_age_s`.
- `stats_age_s` is the difference between the local time of day and the log line time. It wraps at midnight.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. The handler only reads the log file.

## Signature

```http
GET /api/v1/pipelines/{pipeline_id}/queue-stats
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Path

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `pipeline_id` | `str` | none | Yes | Pipeline identifier of 1 to 100 letters, digits, `_` or `-`. |

## Returns

`QueueStatsResponse`.

| Field | Type | Description |
|---|---|---|
| `total_frames` | `int` | Frames processed. |
| `dropped_frames` | `int` | Frames dropped. |
| `avg_latency_ms` | `float` | Average latency in milliseconds. |
| `seconds_since_last_success` | `float` or null | Seconds since the last successful request. |
| `requests_since_last_success` | `int` | Requests since the last success. |
| `healthy` | `bool` | Health flag the server reports. |
| `imdecode_queue_used` | `int` | Entries in use in the image-decode queue. |
| `imdecode_queue_depth` | `int` | Capacity of the image-decode queue. |
| `pending_requests` | `int` | Requests waiting. |
| `node_queues` | `list[dict]` | Per-node queue statistics. |
| `stats_age_s` | `float` | Seconds since the log line was written. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `pipeline_id` has an invalid form. | Use letters, digits, `_` or `-`. |
| 404 | The log is missing or has no stats line in its tail. | Wait for the pipeline to log, or check the id. |
| 500 | The `STATS_JSON` payload is malformed. | Check the stats log of the pipeline. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/pipelines/demo/queue-stats"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  "$BASE/api/v1/pipelines/demo/queue-stats")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.pending_requests' "$resp"
```

## Edge Cases

- The route reads the log of any pipeline id, including one the server does not track.

## Related APIs

| API | Relationship |
|---|---|
| [pipeline-launch](./pipeline-launch.md) | Starts the pipeline that writes the log. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::get_pipeline_queue_stats` (lines 2628-2665)
- `deployment/host_server.py::QueueStatsResponse` (lines 2596-2625)
