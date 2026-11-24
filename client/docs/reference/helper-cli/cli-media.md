# python -m helper media

## Summary

Downloads the sample videos into the server tree.

## Detailed Description

### Behavior

The command calls `server.fetch_media()`, which waits until the server finishes. It prints one line per file as `<file>: <status> <detail>`. It then logs that the media is in `client/assets/test_images/` of the server tree.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper media
```

## Parameters

None.

## Returns

Stdout holds one line per file. Exit code 0 when no file has status `error`.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | A file has status `error`, the fetch times out, or a request fails. | Check the detail text and the server network access, then retry. |
| 2 | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```bash
python -m helper media
```

## Edge Cases

- A fetch that already runs on the server is joined, not restarted.

## Related APIs

| API | Relationship |
|---|---|
| [server.fetch_media](server.fetch_media.md) | Runs and polls the fetch. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_media` (lines 149-162)
