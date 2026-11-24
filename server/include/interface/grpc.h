
// gRPC server entry point for the pipeline inference service.
// Declares GrpcServerConfig (runtime settings from the command line) and GrpcServer.
#pragma once
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace Ax { class Logger; }

namespace Ax {

/**
 * Runtime settings for GrpcServer, filled in from the command line by main().
 *
 * Attributes:
 *   port (int): TCP port the server listens on (all interfaces). Default 50051.
 *   quota_mb (int): gRPC resource quota in megabytes. Default 500.
 *   max_streams (int): Maximum concurrent gRPC streams; also sizes the frame pool (1.5x).
 *     Default 100.
 *   timeout_s (int): Seconds an Infer call waits for the pipeline result before returning
 *     DEADLINE_EXCEEDED; also bounds the drain wait on shutdown. Default 1.
 *   flush_threshold_ms (int): Not read by the current server code. Default 800.
 *   pipeline_depth (int): Set by --pipeline-depth but not read by the current server code.
 *     Default 15.
 *   imdecode_threads (int): Number of image decode worker threads. main() initialises it to
 *     the hardware concurrency. Default 32.
 *   imdecode_queue_timeout_ms (int): Milliseconds to wait for space in the decode queue
 *     before the request is answered as DROPPED. Default 2000.
 *   imdecode_queue_depth (int): Capacity of the decode queue. Default 1.
 *   memory_release_interval_s (int): Set by --memory-release-interval but not read by the
 *     current server code. 0 means disabled. Default 0.
 *   restart_interval_s (int): Seconds between automatic pipeline restarts; 0 disables.
 *     Default 0.
 *   watchdog_timeout_ms (int): Time without a successful completion, while requests keep
 *     arriving, after which the watchdog restarts the pipeline; 0 disables. Default 0.
 *   output_format (std::string): Pixel format of decoded frames fed to the pipeline: "BGR",
 *     "I420" or "RGBA". Default "BGR".
 *   high_bandwidth (bool): Use the throughput-oriented gRPC channel settings. Default false.
 *   labels (std::vector<std::string>): Class names indexed by class id, one per line of the
 *     labels file.
 *   pipeline_spec_path (std::string): Path to the pipeline JSON spec. Required.
 *   meta_key_roles (std::unordered_map<std::string, std::string>): Maps a net's output meta
 *     key to a role, "keypoints" or "face", used when serialising keypoint results. Keys
 *     without an entry default to "keypoints".
 */
struct GrpcServerConfig {
    int         port                      = 50051;
    int         quota_mb                  = 500;
    int         max_streams               = 100;
    int         timeout_s                 = 1;
    int         flush_threshold_ms        = 800;
    int         pipeline_depth            = 15;
    int         imdecode_threads          = 32;
    int         imdecode_queue_timeout_ms = 2000;
    int         imdecode_queue_depth      = 1;
    int         memory_release_interval_s = 0;
    int         restart_interval_s        = 0;
    int         watchdog_timeout_ms       = 0;
    std::string output_format             = "BGR";
    bool        high_bandwidth            = false;

    std::vector<std::string> labels;

    std::string pipeline_spec_path;

    std::unordered_map<std::string, std::string> meta_key_roles;
};

/**
 * gRPC inference server that runs a pipeline built from a JSON spec.
 *
 * Implementation details live in a private Impl class. serve_forever() builds the pipeline,
 * serves requests, and rebuilds the pipeline on restart requests (signal, watchdog or
 * interval) until shutdown is requested.
 *
 * Note:
 *   Shutdown and restart flags are process-wide, so only one server per process is
 *   supported.
 */
class GrpcServer {
public:
    /**
     * Construct the server and configure the memory allocator.
     *
     * Args:
     *   cfg (const GrpcServerConfig&): Settings; copied.
     *   logger (Ax::Logger&): Logger passed to the pipeline builder; must outlive the server.
     */
    explicit GrpcServer(const GrpcServerConfig &cfg, Ax::Logger &logger);
    ~GrpcServer();

    /**
     * Run the server until shutdown is requested, blocking the calling thread.
     *
     * Installs signal handlers for SIGINT, SIGTERM and two real-time signals (SIGRTMIN+1
     * restarts the pipeline, SIGRTMIN+2 prints statistics). Returns early if the pipeline
     * cannot be built or the gRPC server cannot start.
     */
    void serve_forever();

    /**
     * Ask serve_forever() to shut down and return.
     */
    void request_shutdown();

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}
