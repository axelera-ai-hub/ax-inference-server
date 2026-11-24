# python -m helper vllm up

## Summary

Starts a vLLM server for a compiled artifact.

## Detailed Description

### Behavior

The command reads the artifact from `--artifact`. It derives the instance name with `re.sub(r'[^A-Za-z0-9_-]', '-', artifact)` unless `--name` is given. The device is `--device` or the first healthy device. It calls `server.vllm_up` and prints the base URL. Startup takes 1-2 minutes. When the artifact name contains `vlm`, the log notes up to 8 images per prompt.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper vllm up --artifact NAME [--name NAME] [--port PORT] [--device INDEX] [--thinking] [--temperature T]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | The literal `up`. |
| --artifact | str | none | Yes | Compiled artifact such as `qwen3-0.6b`. |
| --name | str | artifact name with other characters replaced by `-` | No | Instance name. |
| --port | int | 8000 | No | Port to serve on. |
| --device | int | first healthy device | No | Device index. |
| --thinking | flag | off | No | Enable chat-template thinking mode. |
| --temperature | float | 0.0 | No | Sampling temperature. |

## Returns

Stdout holds `http://<host>:<port>`. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | No device is healthy or the launch request fails. | Check the artifact name and the device, then retry. |
| 2 | `--artifact` is missing, or the environment is not set. | Pass `--artifact` from `models list`. |

## Usage Examples

### Basic

```bash
python -m helper vllm up --artifact qwen3-0.6b --port 8000
# http://host:8000
```

## Edge Cases

- `--name` replaces the derived name.
- The `--device` help text states that a device running vLLM is not healthy.

## Related APIs

| API | Relationship |
|---|---|
| [server.vllm_up](server.vllm_up.md) | Sends the launch request. |
| [cli-vllm-status](cli-vllm-status.md) | Lists instances. |
| [cli-vllm-down](cli-vllm-down.md) | Stops an instance. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_vllm` (lines 168-201)
