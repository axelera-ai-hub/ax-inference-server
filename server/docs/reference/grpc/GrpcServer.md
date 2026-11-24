# GrpcServer

## Overview

`Ax::GrpcServer` is the gRPC inference server for one pipeline. It builds a pipeline from a JSON spec and serves the `AxInference` service. It rebuilds the pipeline on a restart request. The shutdown and restart flags are process-wide, so a process supports one server.

## Attributes

The class has no public attributes. The constructor copies a [GrpcServerConfig](GrpcServerConfig.md).

## Methods

| Method | Summary | Page |
|---|---|---|
| `GrpcServer(cfg, logger)` | Copies the settings and configures the memory allocator. | This page |
| `serve_forever()` | Builds the pipeline and serves requests until shutdown. | [GrpcServer-serve_forever](GrpcServer-serve_forever.md) |
| `request_shutdown()` | Sets the process-wide shutdown flag and wakes the serve loop. `serve_forever()` then returns. | This page |
| `~GrpcServer()` | Defaulted destructor. | This page |

## Initialization

```cpp
explicit GrpcServer(const GrpcServerConfig &cfg, Ax::Logger &logger);
```

| Name | Type | Description |
|---|---|---|
| `cfg` | `const GrpcServerConfig &` | Settings. The server copies them. |
| `logger` | `Ax::Logger &` | Logger passed to the pipeline builder. It must outlive the server. |

The constructor maps `output_format` to an internal format. `"I420"` and `"i420"` select I420. `"RGBA"` and `"rgba"` select RGBA. Any other value selects BGR. It then sets the memory release rate of the allocator to 10.0.

## Lifecycle

1. The caller constructs the server.
2. The caller runs `serve_forever()` on one thread. The call blocks.
3. Another thread, or a signal handler, ends the call with `request_shutdown()`, `SIGINT` or `SIGTERM`.

Concurrency behavior depends on the underlying runtime. `request_shutdown()` stores an atomic flag and notifies a condition variable.

## Related Classes

| Class | Relationship |
|---|---|
| [GrpcServerConfig](GrpcServerConfig.md) | Settings the server reads. |
| [PipelineService-Infer](PipelineService-Infer.md) | RPC handler the server registers. |

## Source Reference

- `server/include/interface/grpc.h::GrpcServer` (lines 82-111)
- `server/src/interface/grpc.cpp::Ax::GrpcServer` (lines 1380-1384)
