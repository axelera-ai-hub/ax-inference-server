# python -m helper models list

## Summary

Prints the models known to the server, grouped by kind.

## Detailed Description

### Behavior

The command calls `server.list_models()`. For each kind it prints `<kind>:` followed by one name per line, indented by two spaces. The kinds are `prebuilt`, `vision_built`, `vlm_built` and `vllm_artifacts`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper models list
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | The literal `list`. |

## Returns

Stdout holds the grouped names. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable or answers with a non-200 status. | Check the URL, the API key and the server log, then retry. |
| 2 | `HOST_SERVER_URL` or `HOST_SERVER_API_KEY` is unset or empty. | Export both variables. |

## Usage Examples

### Basic

```bash
python -m helper models list
# prebuilt:
#   yolox-m-coco-onnx
#   ...
```

## Edge Cases

- Positional names, `--device` and `--meta-key` are ignored for `list`.
- An empty kind prints its header line with no names.

## Related APIs

| API | Relationship |
|---|---|
| [server.list_models](server.list_models.md) | Collects the lists. |
| [cli-models-provision](cli-models-provision.md) | Provisions a prebuilt model by name. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_models` (lines 47-61)
