# Server reference

## Overview

This reference documents the public API of the inference server. Each area has an `index.md` that lists every page in the area.
The concept pages explain how the parts fit together. Start with [../README.md](../README.md).

## Areas

| Area | Description | Concept page |
|---|---|---|
| [host_server](host_server/index.md) | REST routes of the control plane `host_server.py`. | [host-server.md](../host-server/host-server.md) |
| [grpc](grpc/index.md) | The C++ `GrpcServer` class, its configuration and the `Infer` handler. | [grpc.md](../interfaces/grpc.md) |
| [proto](proto/index.md) | Messages, enum and service of the `AxInference` protocol. | [grpc.md](../interfaces/grpc.md) |
| [nodes](nodes/index.md) | Pipeline nodes, predicates and the builder. | [pipeline.md](../vision/pipeline.md) |
| [image-decoding](image-decoding/index.md) | Image decoder classes and format detection. | [image-decoding.md](../vision/image-decoding.md) |
| [axplugin](axplugin/index.md) | The vLLM plugin for Metis artifacts and `serve.sh`. | [axplugin.md](../vllm/axplugin.md) |

## Related

- [Client reference](../../../client/docs/reference/index.md)
