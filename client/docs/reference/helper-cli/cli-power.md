# python -m helper power

## Summary

Reads or sets the power limit of one device.

## Detailed Description

### Behavior

With `get`, the command prints the limit in watts, or `unset`. With `set`, it sends the limit and prints the limit after the change. The device is `--device` or the first healthy device.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Both environment variables `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` must be set.

## Signature

```bash
python -m helper power get|set [--device INDEX] [--limit WATTS|off]
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| action | str | none | Yes | `get` or `set`. |
| --device | int | first healthy device | No | Device index. |
| --limit | str | none | Yes for `set` | Watts as a number, or `off`. |

## Returns

Stdout holds the limit in watts or `unset`. Exit code 0 on success.

## Exceptions

| Exit code | Trigger | Recovery |
|---|---|---|
| 0 | The command succeeded. | None. |
| 1 | The axdevice call reports failure or a request fails. | Read the step errors in the message. |
| 2 | `set` has no `--limit`, the limit is not a number or `off`, or the environment is not set. | Pass `--limit WATTS` or `--limit off`. |

## Usage Examples

### Basic

```bash
python -m helper power set --device 0 --limit 25
python -m helper power get --device 0
```

## Edge Cases

- `--limit` is ignored for `get`.

## Related APIs

| API | Relationship |
|---|---|
| [server.axdevice_status](server.axdevice_status.md) | Reads the limit. |
| [server.set_power_limit](server.set_power_limit.md) | Sets the limit. |

## Source Reference

- `client/examples/helper/__main__.py::cmd_power` (lines 64-83)
- `client/examples/helper/__main__.py::main` (lines 326-347)
