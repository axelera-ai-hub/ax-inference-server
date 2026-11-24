# config.cascade

## Summary

Builds the config for a detector, filter and per-crop secondary pipeline, with an optional tertiary stage.

## Detailed Description

### Behavior

Each detected region of interest runs in a loop of `roi_iter`, secondary, `roi_collect` and `loop_guard`, at most 50 iterations. With `conditional` set, a tertiary net runs on a crop only when the secondary keypoint confidence condition holds. With `--devices auto` the function asks for two healthy devices. If that raises `ServerError`, it asks for one, and a second `ServerError` propagates. With an explicit list, `healthy_devices` returns every listed device or raises, and the function uses the first two. On one device the stages split the cores. Without core options, one device gives the detector 2 cores, the secondary 2 cores (1 when conditional) and the tertiary 1 core. Two devices give 4 cores to the detector, 4 to the secondary (2 when conditional) and 2 to the tertiary.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The server must be reachable and both `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set. `CORES_PER_DEVICE` is 4.

## Signature

```python
def cascade(args, conditional: bool) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| args | argparse.Namespace | none | Yes | Parsed `config cascade` or `config cascade3` options. |
| conditional | bool | none | Yes | `True` adds the tertiary stage behind a keypoint condition. |

## Returns

`str`. The config as YAML with the sections `global`, `nets`, `predicates` and `pipelines`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | The stages claim more than `CORES_PER_DEVICE` (4) cores on one device, or a requested device is not present. | Pass `--detector-cores`, `--secondary-cores` or `--tertiary-cores`. |
| `ServerError` | The device query fails, the server has no devices, or no listed or auto-selected device is healthy. With `auto`, this follows a failed one-device fallback. | Check device health. |

## Edge Cases

- A core option of 0 counts as unset.
- An empty `--classes` string leaves out the class filter.
- With `args.pin`, one CPU group covers all devices of the pipeline.

## Related APIs

| API | Relationship |
|---|---|
| [cli-config-cascade](cli-config-cascade.md) | Two-stage command. |
| [cli-config-cascade3](cli-config-cascade3.md) | Three-stage command. |
| [config.axnet_path](config.axnet_path.md) | Builds the net paths. |
| [server.pin_groups](server.pin_groups.md) | Plans pinning. |

## Source Reference

- `client/examples/helper/config.py::cascade` (lines 114-190)
