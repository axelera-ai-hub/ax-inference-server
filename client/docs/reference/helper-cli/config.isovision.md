# config.isovision

## Summary

Builds the config for N independent single-detector pipelines and returns it as YAML.

## Detailed Description

### Behavior

Each pipeline gets its own net on `--devices-per-pipeline` devices and a gRPC port of `--port` plus its index. Pipeline ids are `iso-detect`, `iso-detect-0`, `iso-detect-1`, and so on. Each pipeline has a `net` node and a `sink` node, `im_decode_output_format` `I420` and `timeout` 60. With `args.pin`, it adds `taskset_cpus` and `membind` from [server.pin_groups](server.pin_groups.md). The image decode settings come from the `args` or `DEFAULT_IMDECODE`.

### Concurrency

The call blocks the calling thread until the HTTP request returns or times out.

### Constraints

The server must be reachable. The `global` section uses the `GLOBAL` constants of the module.

## Signature

```python
def isovision(args) -> str
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| args | argparse.Namespace | none | Yes | Parsed `config isovision` options. The function reads `pipelines`, `devices_per_pipeline`, `devices`, `cores`, `model`, `meta_key`, `port`, `pin` and the three `imdecode_*` fields. |

## Returns

`str`. The config as YAML with the sections `global`, `nets` and `pipelines`.

## Exceptions

| Exception | Trigger | Recovery |
|---|---|---|
| `UsageError` | Fewer than pipelines x devices-per-pipeline devices are available. | Lower the counts or free devices. |
| `ServerError` | The device query fails or a requested device is unhealthy. | Check device health. |

## Edge Cases

- The function queries the server, so `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.
- `meta_key_override` appears only when `args.meta_key` is set.

## Related APIs

| API | Relationship |
|---|---|
| [cli-config-isovision](cli-config-isovision.md) | Command wrapper. |
| [config.axnet_path](config.axnet_path.md) | Builds the net path. |
| [server.healthy_devices](server.healthy_devices.md) | Selects devices. |

## Source Reference

- `client/examples/helper/config.py::isovision` (lines 74-111)
