# python -m helper devices

## Summary

Health-checks devices and prints the healthy device indexes.

## Detailed Description

### Behavior

Without `--first`, the command calls `server.healthy_devices(--devices, --num-devices)` and prints the indexes as a comma-separated list. With `--first`, it calls `server.select_first_healthy(--preferred)` and prints one index. Per-device health goes to stderr.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper devices [--devices SPEC] [--num-devices N] [--first] [--preferred INDEX]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| --devices | str | `auto` | No | `auto`, one index such as `0`, or a list such as `0,1,2`. |
| --num-devices | int | 1 | No | With `--devices auto`: how many healthy devices to return. |
| --first | flag | off | No | Print only the index of the first healthy device. |
| --preferred | int | 0 | No | With `--first`: the device tried first. |

## Returns

Stdout holds a comma-separated list of indexes, or one index with `--first`. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | No devices exist, too few are healthy, or a requested device is unhealthy. | Pick another device or use `--devices auto`. |
| 2 | A requested device is not present, or the environment is not set. | Use an index the server reports. |

## Usage Examples

### Basic

```bash
python -m helper devices --devices auto --num-devices 2
# 0,1
```

### Production

```bash
DEV=$(python -m helper devices --first) || exit 1
echo "using device $DEV"
```

## Edge Cases

- `--first` ignores `--devices` and `--num-devices`.
- An explicit `--devices` list returns exactly that list or fails.

## Related APIs

| API | Relationship |
|---|---|
| [server.healthy_devices](server.healthy_devices.md) | Selects and health-checks the devices. |
| [server.select_first_healthy](server.select_first_healthy.md) | Selects the device for `--first`. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_devices` (lines 25-36)
