# MCP resources

## Summary

The MCP server publishes two text resources, `docs://client` and `docs://server`, that return the documentation indexes of the repository.

## Detailed Description

### Behavior

Each resource reads a README from disk on every request and returns its text. A read failure does not raise. The resource returns the string `(failed to read <path>: <error>)`.

### Concurrency

Concurrency behavior depends on the underlying runtime.

### Constraints

- The resources need no running GUI app.
- The paths derive from the module location: `client/docs/README.md` and `server/docs/README.md`.
- The tool `get_documentation` returns the same content for clients that cannot fetch resources mid-task.

## Resources

| URI | Name | MIME type | Content |
|---|---|---|---|
| `docs://client` | `client-docs` | `text/markdown` | `client/docs/README.md`, the index of the client library and GUI docs. |
| `docs://server` | `server-docs` | `text/markdown` | `server/docs/README.md`, the index of the inference server docs. |

## Usage Examples

### MCP request

```json
{"method": "resources/read", "params": {"uri": "docs://client"}}
```

### Tool equivalent

```json
{"name": "get_documentation", "arguments": {"which": "client"}}
```

## Edge Cases

- Re-read the resources during a task. The content reflects the files at read time.
- `get_documentation` wraps each README as `{"path": ..., "content": ...}`. The resource returns raw text.

## Related APIs

| API | Relationship |
|---|---|
| [get_documentation](mcp/get_documentation.md) | Tool form of the same data. |
| [agent_mcp_server](agent_mcp_server.md) | Defines the resources. |

## Source Reference

- `client/ui/gui/agent_mcp_server.py::client_docs_resource` (lines 68-76)
- `client/ui/gui/agent_mcp_server.py::server_docs_resource` (lines 79-87)
