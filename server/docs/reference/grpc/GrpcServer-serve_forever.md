# GrpcServer::serve_forever

## Summary

`serve_forever()` builds the pipeline, serves requests, and rebuilds the pipeline on restart until shutdown.

## Detailed Description

### Behavior

The method installs handlers for `SIGINT`, `SIGTERM`, `SIGRTMIN+1` and `SIGRTMIN+2`. Each loop iteration runs these steps.

1. Build the pipeline from `pipeline_spec_path`.
2. Create a frame pool of `max_streams * 1.5` frames.
3. Create the service and start the decode and output workers.
4. Start the gRPC server on `0.0.0.0:<port>` without TLS.
5. Mark the service ready and wait.
6. Leave the wait on shutdown, a restart request, or when `restart_interval_s` elapses.
7. Stop the gRPC server, stop the inputs, drain the pipeline, stop the outputs and log statistics.

`SIGRTMIN+1` and a watchdog trigger request a restart. `SIGRTMIN+2` logs statistics and keeps serving. After a restart with `restart_interval_s` greater than 0, the loop sleeps 1 second before it rebuilds. In the default channel mode the quota allows 2500 threads. `high_bandwidth` replaces the channel settings with a throughput set.

### Concurrency

The method blocks the calling thread. Concurrency behavior depends on the underlying runtime.

### Constraints

- Only one `GrpcServer` per process works.
- The method returns at once if the pipeline build throws. It prints `FATAL: PipelineBuilder::build() failed`.
- The method returns at once if the gRPC server fails to start.

## Signature

```cpp
void serve_forever();
```

## Parameters

None.

## Returns

`void`. The method returns after shutdown or after a startup failure.

## Exceptions

The method catches exceptions from the pipeline build and returns. It declares no other exceptions.

## Edge Cases

- A pipeline build failure during a restart also ends the call, and the server stops serving.
- `request_shutdown()` called before `serve_forever()` makes the loop exit without building a pipeline.

## Related APIs

| API | Relationship |
|---|---|
| [GrpcServer](GrpcServer.md) | Owning class. |
| [GrpcServerConfig](GrpcServerConfig.md) | Settings the loop reads. |
| [PipelineService-Infer](PipelineService-Infer.md) | RPC handler served by the loop. |

## Source Reference

- `server/src/interface/grpc.cpp::Ax::GrpcServer::serve_forever` (lines 1388-1390)
- `server/include/interface/grpc.h::GrpcServer::serve_forever` (lines 101-101)
