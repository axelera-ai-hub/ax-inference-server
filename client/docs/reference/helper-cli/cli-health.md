# python -m helper health

## Summary

Checks that the host server answers `GET /api/v1/health`.

## Detailed Description

### Behavior

The command reads `HOST_SERVER_URL`, sends an unauthenticated GET to `/api/v1/health` and logs `server healthy: <reply>` on stderr. It prints nothing on stdout.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Only `HOST_SERVER_URL` must be set.

## Signature

```bash
python -m helper health
```

## Parameters

None.

## Returns

Stdout is empty. The reply is logged on stderr. Exit code 0 when the server answers.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The request fails or returns an HTTP error status. | Check that the server runs and the URL is correct. |
| 2 | `HOST_SERVER_URL` is unset. | Export `HOST_SERVER_URL`. |

## Usage Examples

### Basic

```bash
export HOST_SERVER_URL=http://host:8000
python -m helper health
```

## Edge Cases

- The command does not need `HOST_SERVER_API_KEY`.

## Related APIs

| API | Relationship |
|---|---|
| [server.check_health](server.check_health.md) | Performs the request. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_health` (lines 19-22)
