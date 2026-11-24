# `POST /api/v1/pipelines/launch`

## Summary

Launches `axinferencenet_grpc` for a stored pipeline spec and waits up to 60 s for its port to open.

## Detailed Description

### Behavior

- The handler resolves `spec_path` and checks that the file lies under `SDK_ROOT/pipeline_specs`.
- The handler shuts down any process that this server tracks under the same `pipeline_id`.
- `launch_remote.launch_one_with_retry` starts the binary and waits up to 60 s for the port on `127.0.0.1`. It makes up to 3 attempts and retries only when a signal killed the process.
- The command runs under `bash` with the SDK venv active. With `taskset_cpus` set, `numactl --physcpubind=<cpus>` prefixes the command, and `membind` adds `--membind=<node>`.
- The server writes its stats log to `SDK_ROOT/pipeline_specs/<pipeline_id>/axinferencenet_uring.log`.
- The handler records the process under `pipeline_id` in an in-memory table.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the process table. The request blocks until the port opens or the launch fails.

### Constraints

- `pipeline_id` must be 1 to 100 characters of letters, digits, `_` or `-`.
- `AXINFERENCENET_BIN_PATH` defaults to `server/build/axinferencenet_grpc`.
- `membind` has no effect unless `taskset_cpus` is set.

## Signature

```http
POST /api/v1/pipelines/launch
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `pipeline_id` | `str` | none | Yes | Identifier used to track and stop the process. |
| `port` | `int` | none | Yes | gRPC port the process listens on. |
| `spec_path` | `str` | none | Yes | Pipeline spec JSON under `SDK_ROOT/pipeline_specs`. |
| `taskset_cpus` | `str` or null | null | No | CPU list for `numactl --physcpubind`. |
| `membind` | `int` or null | null | No | NUMA node for `numactl --membind`. |
| `extra_args` | `list[str]` or null | null | No | Arguments appended to the server command. |

## Returns

`PipelineLaunchResponse`.

| Field | Type | Description |
|---|---|---|
| `pid` | `int` | Process id. |
| `port` | `int` | Port the process listens on. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | `spec_path` is outside `SDK_ROOT/pipeline_specs`. | Upload the spec with `POST /api/v1/pipeline-spec`. |
| 404 | `spec_path` does not exist. | Check the path. |
| 500 | `AXINFERENCENET_BIN_PATH` does not exist. | Build the binary or set the variable. |
| 500 | The spec is invalid, or its `global` block lacks `im_decode_output_format`, `timeout_s` or `restart_interval_s`. | Fix the spec and upload it again. |
| 502 | The process exits early or does not open its port within 60 s. | Read the stats log and the process output. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "demo", "port": 50051, "spec_path": "<SDK_ROOT>/pipeline_specs/demo/spec.json"}' \
  "$BASE/api/v1/pipelines/launch"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "demo", "port": 50051, "spec_path": "<SDK_ROOT>/pipeline_specs/demo/spec.json"}' \
  "$BASE/api/v1/pipelines/launch")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.pid' "$resp"
```

## Edge Cases

- Relaunching with a tracked `pipeline_id` stops the earlier process first.
- The handler does not check the port before launch. The port wait succeeds when any listener accepts connections on `127.0.0.1:<port>`.
- A listener that is not the new process can therefore satisfy the wait. The response then reports the new process id.

## Related APIs

| API | Relationship |
|---|---|
| [upload-pipeline-spec](./upload-pipeline-spec.md) | Creates the spec file. |
| [pipeline-shutdown](./pipeline-shutdown.md) | Stops the process. |
| [pipeline-queue-stats](./pipeline-queue-stats.md) | Reads load statistics. |
| [device-numa-plan](./device-numa-plan.md) | Proposes `taskset_cpus` values. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::launch_pipeline` (lines 2725-2765)
- `deployment/host_server.py::PipelineLaunchRequest` (lines 2668-2693)
- `deployment/host_server.py::PipelineLaunchResponse` (lines 2696-2705)
