# python -m helper upload

## Summary

Uploads the compiled specs of a directory to the server.

## Detailed Description

### Behavior

The command calls `deploy.upload(directory)`. It records each saved path in `manifest.json`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper upload DIRECTORY
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | Yes | Output directory of `compile`. |

## Returns

Stdout is empty. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | The directory has no `manifest.json`, or the environment is not set. | Run `compile` first. |

## Usage Examples

### Basic

```bash
python -m helper upload compiled/iso-detect
```

## Edge Cases

- The command rewrites `manifest.json` in place.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.upload](deploy.upload.md) | Performs the upload. |
| [cli-launch](cli-launch.md) | Next step. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_upload` (lines 112-115)
