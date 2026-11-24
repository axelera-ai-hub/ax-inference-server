
#pragma once

// Builds a runnable node graph from a JSON pipeline spec file.

#include <memory>
#include <string>
#include <vector>

#include "AxInferenceNet.hpp"
#include "AxStreamerUtils.hpp"
#include "AxLog.hpp"
#include "pipeline/node.h"
#include "pipeline/frame.h"

namespace Ax {

/**
 * The result of PipelineBuilder::build(): a wired node graph ready to receive frames.
 *
 * Attributes:
 *     entry_node: Node that receives frames submitted to the pipeline.
 *     result_queue: Queue the terminal nodes push finished (or dropped) frames into.
 *     all_nodes: Every node in spec order, used for stop() and queue_occupancy() sweeps.
 *     pipeline_depth: Number of frames to keep in flight, from the spec's global
 *         "pipeline_depth" scaled by the largest net replica count. 0 when the spec
 *         does not set it.
 */
struct BuiltPipeline {
    std::shared_ptr<AxPipelineNode> entry_node;
    std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> result_queue;
    std::vector<std::shared_ptr<AxPipelineNode>> all_nodes;
    int pipeline_depth = 0;
};

/**
 * Constructs a BuiltPipeline from a JSON spec file.
 *
 * Note:
 *     build() requires nlohmann/json at compile time; without it build() fails at runtime.
 */
class PipelineBuilder {
public:
    /**
     * Create a builder for one spec file.
     *
     * Args:
     *     spec_path (std::string): Path to the JSON pipeline spec.
     *     logger (Ax::Logger &): Logger used during construction; must outlive the builder.
     */
    PipelineBuilder(std::string spec_path, Ax::Logger &logger);

    /**
     * Parse the spec, instantiate and wire the nodes.
     *
     * Returns:
     *     BuiltPipeline: Entry node, result queue, all nodes and pipeline depth.
     *
     * Raises:
     *     std::exception: On an unreadable or invalid spec, or when built without nlohmann/json.
     */
    BuiltPipeline build();

private:
    std::string spec_path_;
    Ax::Logger &logger_;
};

}
