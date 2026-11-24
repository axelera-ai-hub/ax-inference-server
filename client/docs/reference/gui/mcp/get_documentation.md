# get_documentation

## Summary

Returns the client and server documentation indexes as text.

## Detailed Description

### Behavior

- Reads `client/docs/README.md` and `server/docs/README.md` from disk and returns their paths and contents.
- The tool exists for MCP clients that cannot fetch the `docs://client` and `docs://server` resources mid-task. See [MCP resources](../mcp-resources.md).
- The tool makes no HTTP call. It works without a running GUI app.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The tool reads local files and needs no GUI app.

## Signature

```python
get_documentation(which: Literal['client','server','all'] = 'all') -> dict
```

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `which` | `'client'`, `'server'` or `'all'` | `'all'` | No | Selects which index to return. |

## Returns

`dict` with the key `client`, `server` or both. Each value is `{"path": str, "content": str}`. An unreadable README yields a `(failed to read ...)` string as `content`.

## Errors

| Error | Trigger | Recovery |
|---|---|---|
| (none) | Read failures do not raise. They appear in `content`. | Check the file path in the `path` key. |



## Usage Examples

### MCP call

```json
{
  "name": "get_documentation",
  "arguments": {
    "which": "client"
  }
}
```

## Edge Cases

- A value other than `client`, `server` or `all` is rejected by the tool schema.
- `which="all"` returns both keys in one dict.

## Related APIs

| API | Relationship |
|---|---|
| [MCP resources](../mcp-resources.md) | The same two indexes as MCP resources. |
| [MCP server module](../agent_mcp_server.md) | Defines the tool. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::get_documentation` (lines 90-110)
