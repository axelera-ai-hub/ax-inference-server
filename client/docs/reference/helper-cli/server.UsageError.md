# UsageError

## Overview

`UsageError` subclasses `RuntimeError`. The helper raises it for missing environment variables, missing arguments and unknown devices. [main](main.md) prints `ERROR: <message>` to stderr and returns exit code 2.

## Attributes

None beyond those of `RuntimeError`.

## Methods

None beyond those of `RuntimeError`.

## Initialization

Construct it with one message string: `UsageError("text")`.

## Lifecycle

The code raises the exception and [main](main.md) catches it. Behavior inferred from code inspection.

## Related Classes

| Class | Relationship |
|---|---|
| [server.ServerError](server.ServerError.md) | Signals server failures, exit code 1. |
| [server.EXIT_CODES](server.EXIT_CODES.md) | Defines the exit codes. |

## Source Reference

- `client/examples/helper/server.py::UsageError` (lines 25-27)
