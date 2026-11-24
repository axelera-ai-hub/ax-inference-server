# python -m helper vllm status

## Summary

Lists the vLLM instances of the server.

## Detailed Description

### Behavior

The command calls `server.vllm_status()` and prints one line per instance: `<name>: http://<host>:<port> running=<bool> pid=<pid> context_length=<n>`. Instances whose name contains `vlm` add `max_images=8`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper vllm status
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | The literal `status`. |

## Returns

Stdout holds one line per instance. Exit code 0 when at least one instance exists and all run, otherwise 1.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | No instance exists, or one is not running. | Start an instance with `vllm up`. |
| 2 | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```bash
python -m helper vllm status
```

## Edge Cases

- The other `vllm` options are ignored.

## Related APIs

| API | Relationship |
|---|---|
| [server.vllm_status](server.vllm_status.md) | Fetches the instances. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_vllm` (lines 168-201)
