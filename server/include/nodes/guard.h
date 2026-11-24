
// Pipeline node that bounds a loop built from ROI iteration nodes.
#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include "AxStreamerUtils.hpp"
#include "pipeline/node.h"
#include "pipeline/predicate.h"

namespace Ax {

/**
 * Configuration for LoopGuardNode.
 *
 * Attributes:
 *   until (std::shared_ptr<Predicate>): Predicate that ends the loop when true; may be null.
 *   max_iters (int): Loop ends once the frame's roi_index reaches this value. Default 3.
 *   dispatch_queue_depth (size_t): Capacity of the internal queue. Default 8.
 *   queue_timeout (std::chrono::milliseconds): Wait for queue space before a frame is
 *     dropped. Default 2000 ms.
 */
struct LoopGuardNodeConfig {
    std::shared_ptr<Predicate> until;
    int max_iters = 3;
    size_t dispatch_queue_depth = 8;
    std::chrono::milliseconds queue_timeout{ 2000 };
};

/**
 * Decides after each loop pass whether to repeat or leave the loop.
 *
 * Frames are queued and handled on an internal dispatch thread. A frame leaves through the
 * exit callback when the predicate is true or roi_index has reached max_iters, otherwise it
 * goes to the continue callback.
 */
class LoopGuardNode : public AxPipelineNode {
public:
    /**
     * Create the node and start its dispatch thread.
     *
     * Args:
     *   cfg (LoopGuardNodeConfig): Node configuration.
     */
    explicit LoopGuardNode(LoopGuardNodeConfig cfg);
    /** Stop the dispatch thread; exceptions are swallowed. */
    ~LoopGuardNode() override;

    /**
     * Queue the frame for the dispatch thread.
     *
     * The frame is dropped, and logged, if the queue stays full for queue_timeout.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame to evaluate.
     */
    void process(std::shared_ptr<Frame> frame) override;
    /**
     * Stop the dispatch queue and join the dispatch thread, waiting at most 5 seconds.
     */
    void stop() override;

    /** Set the successor for frames that stay in the loop. */
    void set_continue(PipelineCallback cb) { continue_cb_ = std::move(cb); }
    /** Set the successor for frames that leave the loop. */
    void set_exit(PipelineCallback cb) { exit_cb_ = std::move(cb); }

private:
    LoopGuardNodeConfig cfg_;
    PipelineCallback continue_cb_;
    PipelineCallback exit_cb_;
    std::unique_ptr<BlockingQueue<std::shared_ptr<Frame>>> dispatch_queue_;
    std::thread dispatch_thread_;
};

}
