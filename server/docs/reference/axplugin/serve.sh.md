# serve.sh

## Summary

Script that serves one compiled Axelera artifact with the vLLM OpenAI-compatible API server.

## Detailed Description

### Behavior

The script runs these steps.

1. It selects the Python interpreter and requires `MODEL` to be a directory.
2. It sets `HF_HUB_OFFLINE=1` and unsets `SETUPTOOLS_USE_DISTUTILS`.
3. It imports `axelera.runtime.axruntime` and `axelera.runtime.axddr` and prints `libaxruntime` and `stage0` paths.
4. It calls `axplugin.hf_adapter.hf_overrides_for(MODEL)` and keeps the JSON result.
5. It adds `--default-chat-template-kwargs '{"enable_thinking": false}'` when `THINKING` is `off`.
6. It adds `--hf-overrides` when the overrides are not `{}`.
7. It changes into the package directory and execs `python -m vllm.entrypoints.openai.api_server`.

The server always receives `--model`, `--port`, `--enforce-eager` and `--additional-config` with `device` and `temperature`. Extra arguments follow and reach the server unchanged. The script logs `serving <MODEL> on http://127.0.0.1:<PORT> (device ..., thinking ...)` to stderr.

### Concurrency

The script starts one server process for one device. Concurrency behavior depends on the underlying runtime.

### Constraints

- `MODEL` is a compiled artifact directory, not a Hugging Face Hub id.
- The script serves one temperature for the whole process.
- The script does not pass `--served-model-name`.

## Signature

```bash
MODEL=<artifact_dir> [PORT=8000] [DEVICE=metis-0:23:0] [THINKING=off] [TEMPERATURE=0.0] \
  [AXELERA_PYTHON=<python>] ./serve.sh [extra vllm args...]
```

## Parameters

Environment variables

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `MODEL` | path | none | Yes | Compiled artifact directory. |
| `AXELERA_PYTHON` | path | `<pkg>/.venv/bin/python`, else `python3` | No | Python interpreter with `vllm` and `axelera.runtime`. |
| `PORT` | int | `8000` | No | Server port. |
| `DEVICE` | string | `metis-0:23:0` | No | Metis device id, passed as `additional_config["device"]`. |
| `THINKING` | string | `off` | No | `off` disables chat-template thinking. Any other value leaves it on. |
| `TEMPERATURE` | float | `0.0` | No | Value for `additional_config["temperature"]`. |

Positional arguments

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `extra vllm args` | strings | none | No | Forwarded to the vLLM API server. |

## Returns

The script does not return on success. It replaces itself with the vLLM server through `exec`.

## Exceptions

Exit codes

| Exit code | Trigger | Recovery |
|---|---|---|
| 1 | `MODEL` is not a directory. | Pass an artifact directory. |
| 1 | The `axelera.runtime` import check fails. | Install the Axelera runtime in the interpreter. |
| non-zero | `MODEL` is unset (bash parameter check). | Set `MODEL`. |
| non-zero | Another command fails (`set -euo pipefail`), for example `hf_overrides_for`. | Read the error on stderr. |
| server exit code | The vLLM server exits after `exec`. | Read the server log. |

## Usage Examples

### Basic

```bash
MODEL=$SDK_DIR/build/qwen3-0.6b/axscript PORT=8010 ./serve.sh
```

### Production

```bash
MODEL=/models/smolvlm2/axscript DEVICE=metis-0:23:0 THINKING=off TEMPERATURE=0.0 \
  ./serve.sh --max-model-len 2048
```

## Edge Cases

- `hf_overrides_for` returns `{}` when `config.json` already lists `architectures`. The script then omits `--hf-overrides`.

## Related APIs

| API | Relationship |
|---|---|
| [hf_overrides_for](hf_overrides_for.md) | Supplies `--hf-overrides`. |
| [AxeleraModelRunner](AxeleraModelRunner.md) | Reads `device` and `temperature` from `additional_config`. |
| [AxeleraPlatform](AxeleraPlatform.md) | Adapts the config to the artifact. |
| [serving.md](../../vllm/serving.md) | Concept page. |

## Source Reference

- `server/vllm/axelera/scripts/serve.sh`
