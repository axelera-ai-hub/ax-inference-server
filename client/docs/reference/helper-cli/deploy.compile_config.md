# deploy.compile_config

## Summary

Validates a config YAML and compiles it into pipeline specs.

## Detailed Description

### Behavior

The function ensures `SDK_ROOT` is set, asking the server `GET /sdk-root` when it is not. It loads the config with the client `load_config`. For every net with `meta_key_override`, it patches the model `meta_key` on the server. It then runs `PipelineCompiler.compile_all()` and writes the specs and `manifest.json`. The manifest holds `doc_id` and one entry per spec with `pipeline_id`, `port`, `file`, `taskset_cpus` and `membind`.

### Concurrency

The call blocks the calling thread until the compile and any HTTP requests finish.

### Constraints

The function calls the server only when `SDK_ROOT` is unset (`GET /sdk-root`) or a net sets `meta_key_override`. In those cases the server must be reachable and both `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```python
def compile_config(config: str, out_dir: str | None) -> Path
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| config | str | none | Yes | Path to the config YAML. |
| out_dir | str \| None | none | Yes | Output directory. `None` selects `compiled/<doc id>`. |

## Returns

`Path`. The output directory.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The file is missing or the config is rejected. The message holds the first 600 characters of the cause. | Fix the path or the config. |
| `UsageError` | The function needs the server and `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset (`require_env`). | Export both variables. |
| `ServerError` | A server request fails. | Check the server and retry. |

## Usage Examples

### Basic

```python
from helper import deploy
out = deploy.compile_config("configs/iso.yaml", None)
print(out)
```

## Edge Cases

- The function adds `client/compiler` and `client/configs/utils` to `sys.path` on first use.
- It creates the output directory when needed.

## Related APIs

| API | Relationship |
|---|---|
| [deploy.doc_id_for](deploy.doc_id_for.md) | Names the default directory. |
| [deploy.upload](deploy.upload.md) | Next step. |
| [cli-compile](cli-compile.md) | Command wrapper. |
| [cli-up-vision](cli-up-vision.md) | Runs compile, upload and launch. |

## Source Reference

- `client/examples/helper/deploy.py::compile_config` (lines 65-103)
