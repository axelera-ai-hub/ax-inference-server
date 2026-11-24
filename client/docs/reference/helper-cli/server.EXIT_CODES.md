# EXIT_OK, EXIT_FAIL, EXIT_USAGE

## Overview

The three module constants define the process exit codes of the helper CLI.

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| `EXIT_OK` | int | 0 | n/a | none | The command succeeded. |
| `EXIT_FAIL` | int | 1 | n/a | none | A server error, or `status` and `vllm status` found a problem. |
| `EXIT_USAGE` | int | 2 | n/a | none | A usage error. |

## Example

```python
from helper.server import EXIT_OK, EXIT_FAIL, EXIT_USAGE
```

## Related

- [server.ServerError](server.ServerError.md) maps to `EXIT_FAIL`.
- [server.UsageError](server.UsageError.md) maps to `EXIT_USAGE`.
- [main](main.md) returns the codes.

## Source Reference

- `client/examples/helper/server.py::EXIT_OK` (lines 17-17)
- `client/examples/helper/server.py::EXIT_FAIL` (lines 17-17)
- `client/examples/helper/server.py::EXIT_USAGE` (lines 17-17)
