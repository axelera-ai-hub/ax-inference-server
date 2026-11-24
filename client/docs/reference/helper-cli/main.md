# main

## Summary

Runs the helper CLI and maps exceptions to exit codes.

## Detailed Description

### Behavior

The function parses `argv` with [build_parser](build_parser.md). It rejects `models provision` without names and `power set` without `--limit` with a `UsageError`. It then calls the handler of the subcommand. It catches `UsageError` (prints `ERROR: <message>`, returns 2) and `ServerError` (prints `FAIL: <message>`, returns 1) on stderr. Invalid arguments make argparse exit with code 2.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

Concept: [Client examples](../../../examples/README.md).

## Signature

```python
def main(argv=None) -> int
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| argv | list[str] \| None | `None` | No | Arguments to parse. `None` selects `sys.argv[1:]`. |

## Returns

`int`. `EXIT_OK` on success, `EXIT_FAIL` on a server error, `EXIT_USAGE` on a usage error.

## Exceptions

None.

## Usage Examples

### Basic

```python
from helper.__main__ import main
raise SystemExit(main(["health"]))
```

## Edge Cases

- `python -m helper` calls `main()` through `raise SystemExit(main())`.
- A handler may return `EXIT_FAIL` itself, as `status` does.

## Related APIs

| API | Relationship |
|---|---|
| [build_parser](build_parser.md) | Builds the parser. |
| [server.EXIT_CODES](server.EXIT_CODES.md) | Exit code constants. |
| [server.ServerError](server.ServerError.md) | Mapped to exit code 1. |
| [server.UsageError](server.UsageError.md) | Mapped to exit code 2. |

## Source Reference

- `client/examples/helper/__main__.py::main` (lines 326-347)
