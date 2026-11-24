
// Pipeline node that routes a frame to one of two successors based on a predicate.
#pragma once

#include <memory>

#include "pipeline/node.h"
#include "pipeline/predicate.h"

namespace Ax {

/**
 * Branching node: sends each frame to the "then" or "else" successor.
 *
 * The predicate is evaluated on the calling thread. If the chosen successor is not set the
 * frame is silently dropped. The generic next callback is not used.
 */
class ConditionNode : public AxPipelineNode {
public:
    /**
     * Create the node.
     *
     * Args:
     *   predicate (std::shared_ptr<Predicate>): Condition evaluated for every frame.
     */
    explicit ConditionNode(std::shared_ptr<Predicate> predicate)
        : predicate_(std::move(predicate))
    {}

    /**
     * Evaluate the predicate and forward the frame to the "then" or "else" successor.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame to route.
     */
    void process(std::shared_ptr<Frame> frame) override
    {
        auto &cb = predicate_->eval(*frame) ? then_ : else_;
        if (cb) cb(std::move(frame));
    }

    /** Ignore the callback; use set_then() and set_else() to wire this node. */
    void set_next(PipelineCallback) override {}

    /** Set the successor used when the predicate is true. */
    void set_then(PipelineCallback cb) { then_ = std::move(cb); }
    /** Set the successor used when the predicate is false. */
    void set_else(PipelineCallback cb) { else_ = std::move(cb); }

private:
    std::shared_ptr<Predicate> predicate_;
    PipelineCallback then_;
    PipelineCallback else_;
};

}
