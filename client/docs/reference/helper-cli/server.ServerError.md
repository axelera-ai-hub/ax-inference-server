# ServerError

## Overview

`ServerError` subclasses `RuntimeError`. [server.api](server.api.md) raises it on a transport error or a non-200 status. [main](main.md) prints `FAIL: <message>` to stderr and returns exit code 1.

## Attributes

None beyond those of `RuntimeError`.

## Methods

None beyond those of `RuntimeError`.

## Initialization

Construct it with one message string: `ServerError("text")`.

## Lifecycle

The code raises the exception and [main](main.md) catches it. Behavior inferred from code inspection.

## Related Classes

| Class | Relationship |
|---|---|
| [server.UsageError](server.UsageError.md) | Signals invalid input, exit code 2. |
| [server.EXIT_CODES](server.EXIT_CODES.md) | Defines the exit codes. |

## Source Reference

- `client/examples/helper/server.py::ServerError` (lines 20-22)
