
// Entry point of the pipeline gRPC inference server.
// Parses command-line flags into a GrpcServerConfig, then runs Ax::GrpcServer until shutdown.
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#include <cstdlib>

#include "interface/grpc.h"
#include "AxLog.hpp"
#include "common/io_uring_logger.hpp"

// Labels file used when none is given; resolved under $AXELERA_FRAMEWORK when that is set.
constexpr auto DEFAULT_LABELS = "ax_datasets/labels/coco.names";

namespace {

/**
 * Read a text file into a list of lines.
 *
 * Args:
 *   path (const std::string&): File to read. A missing or unreadable file yields an empty list.
 *
 * Returns:
 *   std::vector<std::string>: One entry per line.
 */
auto read_labels(const std::string &path)
{
    std::vector<std::string> labels;
    std::ifstream file(path);
    for (std::string line; std::getline(file, line);) {
        labels.push_back(line);
    }
    return labels;
}

/**
 * Build the server configuration from the command line.
 *
 * Recognised options are listed in the usage text printed when --pipeline-spec is missing.
 * A positional argument ending in ".txt" or ".names" is read as the labels file; if none is
 * given the default COCO labels file is used. Unknown "--" flags produce a warning and are
 * skipped together with a following value. imdecode_threads defaults to the hardware
 * concurrency.
 *
 * Args:
 *   argc (int): Argument count from main().
 *   argv (char**): Argument vector from main().
 *
 * Returns:
 *   Ax::GrpcServerConfig: The parsed configuration.
 *
 * Note:
 *   Exits the process with status 1 on an invalid or missing option value, or when
 *   --pipeline-spec is absent (after printing the usage text).
 */
Ax::GrpcServerConfig parse_args(int argc, char **argv)
{
    Ax::GrpcServerConfig cfg;
    cfg.imdecode_threads = static_cast<int>(std::thread::hardware_concurrency());

    for (auto arg = 1; arg != argc; ++arg) {
        auto s = std::string(argv[arg]);

        if (s == "--port") {
            if (arg + 1 < argc) {
                try {
                    cfg.port = std::stoi(argv[++arg]);
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid port number provided." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --port flag requires a port number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--memory-release-interval") {
            if (arg + 1 < argc) {
                try {
                    cfg.memory_release_interval_s = std::stoi(argv[++arg]);
                    if (cfg.memory_release_interval_s < 0) {
                        std::cerr << "Error: --memory-release-interval must be non-negative." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --memory-release-interval value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --memory-release-interval requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--quota-mb") {
            if (arg + 1 < argc) {
                try {
                    cfg.quota_mb = std::stoi(argv[++arg]);
                    if (cfg.quota_mb <= 0) {
                        std::cerr << "Error: --quota-mb must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --quota-mb value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --quota-mb requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--max-streams") {
            if (arg + 1 < argc) {
                try {
                    cfg.max_streams = std::stoi(argv[++arg]);
                    if (cfg.max_streams <= 0) {
                        std::cerr << "Error: --max-streams must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --max-streams value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --max-streams requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--timeout") {
            if (arg + 1 < argc) {
                try {
                    cfg.timeout_s = std::stoi(argv[++arg]);
                    if (cfg.timeout_s <= 0) {
                        std::cerr << "Error: --timeout must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --timeout value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --timeout requires a number." << std::endl;
                std::exit(1);
            }
        }
// Disabled: --flush-threshold is not accepted because flush_threshold_ms is unused.
#if 0
        else if (s == "--flush-threshold") {
            if (arg + 1 < argc) {
                try {
                    cfg.flush_threshold_ms = std::stoi(argv[++arg]);
                    if (cfg.flush_threshold_ms < 0) {
                        std::cerr << "Error: --flush-threshold must be non-negative." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --flush-threshold value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --flush-threshold requires a number." << std::endl;
                std::exit(1);
            }
        }
#endif
        else if (s == "--pipeline-depth") {
            if (arg + 1 < argc) {
                try {
                    cfg.pipeline_depth = std::stoi(argv[++arg]);
                    if (cfg.pipeline_depth <= 0) {
                        std::cerr << "Error: --pipeline-depth must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --pipeline-depth value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --pipeline-depth requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--imdecode-threads") {
            if (arg + 1 < argc) {
                try {
                    cfg.imdecode_threads = std::stoi(argv[++arg]);
                    if (cfg.imdecode_threads <= 0) {
                        std::cerr << "Error: --imdecode-threads must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --imdecode-threads value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --imdecode-threads requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--imdecode-queue-timeout-ms") {
            if (arg + 1 < argc) {
                try {
                    cfg.imdecode_queue_timeout_ms = std::stoi(argv[++arg]);
                    if (cfg.imdecode_queue_timeout_ms < 0) {
                        std::cerr << "Error: --imdecode-queue-timeout-ms must be non-negative." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --imdecode-queue-timeout-ms value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --imdecode-queue-timeout-ms requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--imdecode-queue-depth") {
            if (arg + 1 < argc) {
                try {
                    cfg.imdecode_queue_depth = std::stoi(argv[++arg]);
                    if (cfg.imdecode_queue_depth <= 0) {
                        std::cerr << "Error: --imdecode-queue-depth must be positive." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --imdecode-queue-depth value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --imdecode-queue-depth requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--meta-key-role") {
            if (arg + 1 < argc) {
                std::string kv = argv[++arg];
                auto eq = kv.find('=');
                if (eq == std::string::npos || eq == 0 || eq == kv.size() - 1) {
                    std::cerr << "Error: --meta-key-role requires <key>=<role>." << std::endl;
                    std::exit(1);
                }
                cfg.meta_key_roles[kv.substr(0, eq)] = kv.substr(eq + 1);
            } else {
                std::cerr << "Error: --meta-key-role requires <key>=<role>." << std::endl;
                std::exit(1);
            }
        } else if (s == "--restart-interval") {
            if (arg + 1 < argc) {
                try {
                    cfg.restart_interval_s = std::stoi(argv[++arg]);
                    if (cfg.restart_interval_s < 0) {
                        std::cerr << "Error: --restart-interval must be non-negative." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --restart-interval value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --restart-interval requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--watchdog-timeout-ms") {
            if (arg + 1 < argc) {
                try {
                    cfg.watchdog_timeout_ms = std::stoi(argv[++arg]);
                    if (cfg.watchdog_timeout_ms < 0) {
                        std::cerr << "Error: --watchdog-timeout-ms must be non-negative." << std::endl;
                        std::exit(1);
                    }
                } catch (const std::exception &) {
                    std::cerr << "Error: Invalid --watchdog-timeout-ms value." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --watchdog-timeout-ms requires a number." << std::endl;
                std::exit(1);
            }
        } else if (s == "--output-format") {
            if (arg + 1 < argc) {
                std::string fmt = argv[++arg];
                if (fmt == "I420" || fmt == "i420") {
                    cfg.output_format = "I420";
                    std::cout << "Output format: I420 (YUV 4:2:0)\n";
                } else if (fmt == "RGBA" || fmt == "rgba") {
                    cfg.output_format = "RGBA";
                    std::cout << "Output format: RGBA\n";
                } else if (fmt == "BGR" || fmt == "bgr") {
                    cfg.output_format = "BGR";
                    std::cout << "Output format: BGR (default)\n";
                } else {
                    std::cerr << "Error: --output-format must be 'BGR', 'I420', or 'RGBA'." << std::endl;
                    std::exit(1);
                }
            } else {
                std::cerr << "Error: --output-format requires a format (BGR, I420, or RGBA)." << std::endl;
                std::exit(1);
            }
        } else if (s == "--high-bandwidth") {
            cfg.high_bandwidth = true;
        } else if (s == "--pipeline-spec") {
            if (arg + 1 < argc) {
                cfg.pipeline_spec_path = argv[++arg];
            } else {
                std::cerr << "Error: --pipeline-spec requires a path to a pipeline JSON file." << std::endl;
                std::exit(1);
            }
        // Skip the value of an unknown flag unless it looks like another flag or a labels file.
        } else if (s.starts_with("--")) {
            std::cerr << "Warning: Unknown flag '" << s << "' (ignoring)" << std::endl;
            if (arg + 1 < argc) {
                std::string next = argv[arg + 1];
                if (!next.starts_with("--") && !next.ends_with(".txt") &&
                    !next.ends_with(".names")) {
                    ++arg;
                }
            }
        } else if (s.ends_with(".txt") || s.ends_with(".names")) {
            cfg.labels = read_labels(s);
        } else if (!std::filesystem::exists(s)) {
            std::cerr << "Warning: Path does not exist: " << s << std::endl;
        }
    }

    if (cfg.pipeline_spec_path.empty()) {
        std::cerr
            << "Usage: " << argv[0] << " --pipeline-spec <path.json> [options]\n"
            << "\n"
            << "Positional arguments:\n"
            << "  labels.txt                 Path to the labels file (optional, default: "
            << DEFAULT_LABELS << ")\n"
            << "\n"
            << "Options:\n"
            << "  --pipeline-spec <path>     Path to a pipeline JSON spec (required)\n"
            << "  --port <number>            TCP port (default: 50051)\n"
            << "  --quota-mb <number>        gRPC resource quota in MB (default: 500)\n"
            << "  --max-streams <number>     Max concurrent gRPC streams (default: 100)\n"
            << "  --timeout <seconds>        Request timeout (default: 1)\n"
            << "  --pipeline-depth <num>     Pipeline depth estimate (default: 15)\n"
            << "  --imdecode-threads <num>   Threads for cv::imdecode (default: hardware_concurrency)\n"
            << "  --imdecode-queue-timeout-ms <ms>  Bounded-wait timeout pushing a decoded frame into\n"
            << "                             imdecode_queue_ before reporting DROPPED (default: 2000)\n"
            << "  --imdecode-queue-depth <num>  Capacity of imdecode_queue_ (default: 1) -- decode\n"
            << "                             thread pool size (--imdecode-threads) is unaffected;\n"
            << "                             a deeper queue trades drop rate for queueing latency\n"
            << "  --memory-release-interval <seconds>  Interval for memory release (default: 0 = disabled)\n"
            << "  --restart-interval <seconds>         Interval for server restart (default: 0 = disabled)\n"
            << "  --watchdog-timeout-ms <ms>  Health-watchdog auto-restart threshold (default: 0 = disabled)\n"
            << "  --output-format <format>   Output pixel format: BGR, I420, or RGBA (default: BGR)\n"
            << "  --high-bandwidth           Enable high-throughput mode\n"
            << "  --meta-key-role <key>=<role>  Role (\"keypoints\"|\"face\") for a net's output\n"
            << "                             meta_key, disambiguating AxMetaKptsDetection entries\n"
            << "                             (repeatable; default role is \"keypoints\" if omitted)\n"
            << std::endl;
        std::exit(1);
    }

    if (cfg.labels.empty()) {
        const auto root = std::getenv("AXELERA_FRAMEWORK");
        cfg.labels = read_labels(
            root && root[0] != '\0'
                ? std::string(root) + "/" + DEFAULT_LABELS
                : DEFAULT_LABELS);
    }

    return cfg;
}

}

/**
 * Run the server with the configuration parsed from the command line.
 *
 * Args:
 *   argc (int): Argument count.
 *   argv (char**): Argument vector.
 *
 * Returns:
 *   int: 0 after a clean shutdown. Configuration errors exit the process with status 1.
 */
int main(int argc, char **argv)
{
    Ax::GrpcServerConfig cfg = parse_args(argc, argv);

    Ax::Logger logger;
    Ax::GrpcServer server(cfg, logger);
    server.serve_forever();
    return 0;
}
