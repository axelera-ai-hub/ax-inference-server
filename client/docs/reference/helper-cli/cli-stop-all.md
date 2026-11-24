# python -m helper stop-all

## Summary

Stops every pipeline and vLLM server on the host.

## Detailed Description

### Behavior

The command calls `server.stop_all()`, the equivalent of the GUI Force Stop All. It logs the killed pids and vLLM names.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper stop-all
```

## Parameters

None.

## Returns

Stdout is empty. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```bash
python -m helper stop-all
```

## Edge Cases

- The command takes no options and asks for no confirmation.

## Related APIs

| API | Relationship |
|---|---|
| [server.stop_all](server.stop_all.md) | Sends the request. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_stop_all` (lines 39-44)
