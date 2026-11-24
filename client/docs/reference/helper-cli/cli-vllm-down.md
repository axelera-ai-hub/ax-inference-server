# python -m helper vllm down

## Summary

Stops a vLLM instance by name.

## Detailed Description

### Behavior

The command calls `server.vllm_down(--name)` and logs `stopped` or `not running`. Both outcomes exit with code 0.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper vllm down --name NAME
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | The literal `down`. |
| --name | str | none | Yes | Instance name. |

## Returns

Stdout is empty. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | `--name` is missing, or the environment is not set. | Pass `--name`. |

## Usage Examples

### Basic

```bash
python -m helper vllm down --name qwen3-0.6b
```

## Edge Cases

- An instance the server did not start is reported as not running.

## Related APIs

| API | Relationship |
|---|---|
| [server.vllm_down](server.vllm_down.md) | Sends the shutdown request. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_vllm` (lines 168-201)
