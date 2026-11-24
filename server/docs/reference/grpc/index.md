# gRPC server reference

## Overview

This area documents the public C++ surface of the vision gRPC server. `Ax::GrpcServer` builds a pipeline from a JSON spec and serves the `AxInference` service. `GrpcServerConfig` holds its settings. The concept page is [gRPC interface](../../interfaces/grpc.md). The wire contract is in the [proto reference](../proto/index.md).

## Architecture

```mermaid
flowchart LR
    M[main] --> C[GrpcServerConfig]
    C --> S[GrpcServer]
    S -->|serve_forever| P[PipelineService]
    P -->|Infer| R[FrameResult]
```

## Pages

| Page | Kind | Summary |
|---|---|---|
| [GrpcServer](GrpcServer.md) | class | Serves one pipeline over gRPC and restarts it on request. |
| [GrpcServer-serve_forever](GrpcServer-serve_forever.md) | function | Runs the build, serve and restart loop until shutdown. |
| [GrpcServerConfig](GrpcServerConfig.md) | class | Runtime settings of the server. |
| [PipelineService-Infer](PipelineService-Infer.md) | function | Handles the `Infer` RPC and builds the `FrameResult`. |

## Quick Example

```cpp
Ax::GrpcServerConfig cfg;
cfg.pipeline_spec_path = "pipeline.json";
Ax::GrpcServer server(cfg, logger);
server.serve_forever();
```
