# build_parser

## Summary

Builds the argparse parser with one subparser per subcommand.

## Detailed Description

### Behavior

The parser has the program name `python -m helper` and a required subcommand. The subcommands are `health`, `devices`, `stop-all`, `models`, `power`, `pin`, `config`, `compile`, `upload`, `launch`, `up`, `down`, `status`, `media` and `vllm`. `config` has the nested subcommands `isovision`, `cascade` and `cascade3`. The three `config` examples share the tuning options `--imdecode-threads`, `--imdecode-queue-depth`, `--imdecode-queue-timeout-ms`, `--pin`, `--devices` and `-o/--output`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

## Signature

```python
def build_parser() -> argparse.ArgumentParser
```

## Parameters

None.

## Returns

`argparse.ArgumentParser`. The configured parser.

## Exceptions

None.

## Edge Cases

- Each subparser stores its handler with `set_defaults(func=...)`.

## Related APIs

| API | Relationship |
|---|---|
| [main](main.md) | Parses and dispatches. |
| [cli-health](cli-health.md) | Subcommand page. |
| [cli-config-isovision](cli-config-isovision.md) | Nested subcommand page. |

## Source Reference

- `client/examples/helper/__main__.py::build_parser` (lines 214-323)
