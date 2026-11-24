# `POST /api/v1/vllm/launch`

## Summary

Launches a vLLM server with `serve.sh` and waits up to 180 s for its port.

## Detailed Description

### Behavior

- The handler resolves `artifact`. It expands `${SDK_ROOT}` and treats a relative path as relative to the SDK root.
- The handler shuts down an instance that this server tracks under the same `name`.
- The handler runs `bash <VLLM_AXELERA_DIR>/scripts/serve.sh` with `MODEL`, `PORT`, `DEVICE`, `THINKING`, `TEMPERATURE`, `AXELERA_PYTHON` and `PYTHONPATH` set.
- `THINKING` is `on` when `enable_thinking` is true, otherwise `off`. `PYTHONPATH` is the SDK root.
- Output goes to `<VLLM_LOG_DIR>/<name>.log`. Each launch truncates the file.
- The handler reads `context_len` from `vlm.json`, then `pipeline.json`, in the artifact directory.

### Concurrency

FastAPI runs this synchronous handler in a worker thread. A lock guards the vLLM table. The request blocks until the port opens or the launch fails.

### Constraints

- `name` must be 1 to 100 characters of letters, digits, `_` or `-`.
- `VLLM_AXELERA_DIR` defaults to `server/vllm/axelera`.
- `VLLM_VENV_PYTHON` defaults to `.venv-vllm/bin/python3` in the repository root.
- `VLLM_LOG_DIR` defaults to `deployment/vllm_logs`.

## Signature

```http
POST /api/v1/vllm/launch
X-API-Key: <DEPLOYMENT_API_KEY>
```

## Parameters

### Body

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `str` | none | Yes | Identifier that tracks the instance and names its log. |
| `artifact` | `str` | none | Yes | Artifact directory. It can start with `${SDK_ROOT}`. |
| `port` | `int` | none | Yes | Port to serve on. |
| `device` | `str` | none | Yes | Value exported to `serve.sh` as `DEVICE`. |
| `enable_thinking` | `bool` | `false` | No | Sets `THINKING` to `on` or `off`. |
| `temperature` | `float` | 0.0 | No | Sampling temperature exported as `TEMPERATURE`. |

## Returns

`VllmLaunchResponse`.

| Field | Type | Description |
|---|---|---|
| `pid` | `int` | Process id. |
| `port` | `int` | Port being served. |
| `context_length` | `int` or null | Context length read from the artifact, if known. |

## Status codes

| Code | Trigger | Recovery |
|---|---|---|
| 401 | `X-API-Key` is missing or wrong. | Send the correct `X-API-Key` header. |
| 500 | `DEPLOYMENT_API_KEY` is not set on the server. | Set `DEPLOYMENT_API_KEY` on the server and restart it. |
| 500 | `SDK_ROOT` is unset or not a directory. | Set `SDK_ROOT` to an existing directory. |
| 400 | The artifact directory does not exist. | List artifacts with `GET /api/v1/vllm/artifacts`. |
| 500 | `serve.sh` or the vLLM venv Python is missing. | Run `setup.sh --vllm-axplugin`. |
| 502 | The server exits early or does not open its port within 180 s. | Read the log file named in the detail. |
| 422 | The request fails schema validation. | Fix the request to match the schema. |

## Usage Examples

### Basic

```bash
BASE="http://<host>:8088"
curl -sS \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "llm", "artifact": "${SDK_ROOT}/build/my-llm/axscript", "port": 8000, "device": "0"}' \
  "$BASE/api/v1/vllm/launch"
```

### Production

```bash
BASE="http://<host>:8088"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w '%{http_code}' \
  -X POST \
  -H "X-API-Key: $DEPLOYMENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "llm", "artifact": "${SDK_ROOT}/build/my-llm/axscript", "port": 8000, "device": "0"}' \
  "$BASE/api/v1/vllm/launch")
if [ "$status" != "200" ]; then echo "HTTP $status" >&2; cat "$resp" >&2; exit 1; fi
jq '.context_length' "$resp"
```

## Edge Cases

- On a 502 the handler does not track the process and does not stop it. A process that stays alive keeps running.
- `POST /api/v1/pipelines/cleanup-all` does not stop an untracked vLLM process. Stop it by pid.
- `context_length` is null when no manifest provides `context_len`.

## Related APIs

| API | Relationship |
|---|---|
| [vllm-artifacts](./vllm-artifacts.md) | Lists artifacts to launch. |
| [vllm-status](./vllm-status.md) | Shows tracked instances. |
| [vllm-shutdown](./vllm-shutdown.md) | Stops the instance. |
| [vLLM serving](../../vllm/serving.md) | Concept page for vLLM serving. |
| [Host server](../../host-server/host-server.md) | Concept page for the host server. |

## Source Reference

- `deployment/host_server.py::launch_vllm` (lines 2962-3022)
- `deployment/host_server.py::VllmLaunchRequest` (lines 2920-2945)
- `deployment/host_server.py::VllmLaunchResponse` (lines 2948-2959)
