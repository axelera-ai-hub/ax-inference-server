# python -m helper pin

## Summary

Prints the CPU list and NUMA node planned for each group of healthy devices.

## Detailed Description

### Behavior

The command reads the CPU topology, selects healthy devices and splits them into groups of `--devices-per-pipeline`. It then prints `devices <list>: taskset_cpus=<ranges> membind=<node>` per group.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper pin [--devices SPEC] [--num-devices N] [--devices-per-pipeline N] [--cores-per-device N]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| --devices | str | `auto` | No | `auto` or a list such as `0,1`. |
| --num-devices | int | 4 | No | With `auto`: how many healthy devices. |
| --devices-per-pipeline | int | 1 | No | Group size. |
| --cores-per-device | int | 4 | No | CPU cores reserved per device. |

## Returns

Stdout holds one line per group. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The server is unreachable, answers with a non-200 status, or `healthy_devices` raises `ServerError` (no devices, too few healthy, or a requested device unhealthy). | Check the URL, the API key, the device health and the server log, then retry. |
| 2 | A requested device is not present, or the environment is not set. | Use an index the server reports. |

## Usage Examples

### Basic

```bash
python -m helper pin --num-devices 2 --devices-per-pipeline 1
```

## Edge Cases

- `membind` is `None` when NUMA is not available.

## Related APIs

| API | Relationship |
|---|---|
| [server.cpu_topology](server.cpu_topology.md) | Reads the topology. |
| [server.pin_groups](server.pin_groups.md) | Plans the pinning. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_pin` (lines 86-94)
