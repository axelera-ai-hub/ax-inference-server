
#pragma once

// Base interface for pipeline nodes.

#include <functional>
#include <memory>
#include <optional>
#include <string>

#include "pipeline/frame.h"

namespace Ax {

/** Callback invoked with a frame to hand it to the next stage. */
using PipelineCallback = std::function<void(std::shared_ptr<Frame>)>;

/**
 * Abstract base class of all pipeline nodes.
 *
 * A node receives frames through process() and forwards them to the callback set by
 * set_next().
 */
class AxPipelineNode {
public:
    virtual ~AxPipelineNode() = default;

    /**
     * Handle one frame.
     *
     * Args:
     *     frame (std::shared_ptr<Frame>): The frame to process.
     */
    virtual void process(std::shared_ptr<Frame> frame) = 0;

    /** Set the callback that receives this node's output frames. */
    virtual void set_next(PipelineCallback cb) { next_ = std::move(cb); }

    /** Stop internal threads and queues. The default does nothing. */
    virtual void stop() {}

    /**
     * Snapshot of a node's queue fill levels.
     *
     * Attributes:
     *     node_id: Identifier of the reporting node.
     *     input_used: Items currently in the input queue.
     *     input_depth: Capacity of the input queue.
     *     result_used: Items currently in the result queue.
     *     result_depth: Capacity of the result queue.
     */
    struct QueueOccupancy {
        std::string node_id;
        size_t input_used = 0;
        size_t input_depth = 0;
        size_t result_used = 0;
        size_t result_depth = 0;
    };
    /**
     * Report queue fill levels.
     *
     * Returns:
     *     std::optional<QueueOccupancy>: Occupancy, or std::nullopt for nodes without queues.
     */
    virtual std::optional<QueueOccupancy> queue_occupancy() const { return std::nullopt; }

protected:
    PipelineCallback next_;
};

}
