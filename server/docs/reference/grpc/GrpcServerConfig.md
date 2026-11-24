# GrpcServerConfig

## Overview

`GrpcServerConfig` holds the runtime settings of one `Ax::GrpcServer`. The function `main()` fills it from command-line options. `GrpcServer` copies the struct at construction. The tuning trade-offs are in [tuning.md](../../tuning/tuning.md).

## Fields

| Field | Type | Default | Required | Constraints | Description |
|---|---|---|---|---|---|
| `port` | `int` | `50051` | No | none | TCP port. The server listens on all interfaces. |
| `quota_mb` | `int` | `500` | No | `main()` requires a positive value. | gRPC resource quota in megabytes. |
| `max_streams` | `int` | `100` | No | `main()` requires a positive value. | Concurrent stream limit. It also sizes the frame pool at `max_streams * 1.5` frames. |
| `timeout_s` | `int` | `1` | No | `main()` requires a positive value. | Seconds `Infer` waits for a result. It also bounds the drain wait on shutdown. |
| `imdecode_threads` | `int` | `32` in the struct | No | `main()` requires a positive value. | Number of decode worker threads. `main()` initialises it to the hardware concurrency. |
| `imdecode_queue_timeout_ms` | `int` | `2000` | No | `main()` requires a non-negative value. | Milliseconds to wait for space in the decode queue before the request is `DROPPED`. |
| `imdecode_queue_depth` | `int` | `1` | No | `main()` requires a positive value. | Capacity of the decode queue. |
| `restart_interval_s` | `int` | `0` | No | `main()` requires a non-negative value. | Seconds between automatic pipeline restarts. 0 disables. |
| `watchdog_timeout_ms` | `int` | `0` | No | `main()` requires a non-negative value. | Time without a successful completion, while requests keep arriving, that triggers a watchdog restart. The watchdog also requires a minimum number of attempts. 0 disables. |
| `output_format` | `std::string` | `"BGR"` | No | `"BGR"`, `"I420"` or `"RGBA"`. Other values select BGR. | Pixel format of decoded frames. |
| `high_bandwidth` | `bool` | `false` | No | none | Selects the throughput-oriented gRPC channel settings. |
| `labels` | `std::vector<std::string>` | empty in the struct; `main()` loads `ax_datasets/labels/coco.names` when no labels file is given | No | none | Class names indexed by class id. |
| `pipeline_spec_path` | `std::string` | empty | Yes | none | Path to the pipeline JSON spec. |
| `meta_key_roles` | `std::unordered_map<std::string, std::string>` | empty | No | `main()` requires the form `<key>=<role>`. | Maps a meta key to a role. The role `"face"` selects face handling. Any other role selects keypoints. |

## Example

```cpp
Ax::GrpcServerConfig cfg;
cfg.pipeline_spec_path = "pipeline.json";
cfg.port = 50051;
cfg.timeout_s = 5;
cfg.output_format = "BGR";
```

## Related

- [GrpcServer](GrpcServer.md)
- [PipelineService-Infer](PipelineService-Infer.md)
- [gRPC interface](../../interfaces/grpc.md)

## Source Reference

- `server/include/interface/grpc.h::GrpcServerConfig` (lines 48-69)
- `server/src/main.cpp::main` (lines 376-384)
