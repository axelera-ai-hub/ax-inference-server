# deploy.upload

## Summary

Uploads each compiled spec to the server and records its saved path in the manifest.

## Detailed Description

### Behavior

The function reads `manifest.json` and posts each spec file to `/pipeline-spec`. It stores the returned `saved_path` in the manifest entry and rewrites the manifest.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

`directory` must hold a `manifest.json` written by `compile`.

## Signature

```python
def upload(directory: str) -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| directory | str | none | Yes | Output directory of `compile`. |

## Returns

`dict`. The updated manifest.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The directory has no `manifest.json`. | Run `compile` first. |
| `ServerError` | The request fails or the server answers with a non-200 status. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import deploy
manifest = deploy.upload("compiled/iso-detect")
```

## Edge Cases

- Running the function again uploads every spec again.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.compile_config](deploy.compile_config.md) | Creates the manifest. |
| [deploy.launch](deploy.launch.md) | Next step. |
| [cli-upload](cli-upload.md) | Command wrapper. |

## Source Reference

- `client/examples/helper/deploy.py::upload` (lines 118-135)
