
// Pipeline node that runs a model through an AxInferenceNet.
#pragma once

#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <thread>

#include "AxInferenceNet.hpp"
#include "AxLog.hpp"
#include "AxStreamerUtils.hpp"
#include "pipeline/node.h"

namespace Ax {

/**
 * Pipeline node that wraps an AxInferenceNet with bounded queues and worker threads.
 *
 * Frames enter an input queue, a push thread feeds them to the inference net, and completed
 * frames pass through a result queue to a drain thread that calls the next node. When a
 * queue stays full past its timeout the frame is dropped, logged, and (if a drop sink was
 * given) reported to it with dropped set.
 */
class InferenceNode : public AxPipelineNode {
public:
    /**
     * Create the node, its queues and the inference net, and start the worker threads.
     *
     * Args:
     *   node_id (std::string): Identifier used in log messages and drop reasons.
     *   props (const InferenceNetProperties&): Model and device settings for the net.
     *   logger (Ax::Logger&): Logger handed to the inference net.
     *   queue_timeout (std::chrono::milliseconds, optional): Wait for space in the input queue
     *     before dropping a frame. Defaults to 2000 ms.
     *   drop_sink (std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>>, optional): Queue that
     *     receives dropped frames so the client can be told. Defaults to null (log only).
     *   join_timeout (std::chrono::milliseconds, optional): Per-thread wait during stop().
     *     Defaults to 5000 ms.
     *   queue_depth (size_t, optional): Capacity of the input and result queues. Defaults to 1.
     *   done_callback_timeout (std::chrono::milliseconds, optional): Wait for space in the
     *     result queue when the net completes a frame. Defaults to 50 ms.
     */
    InferenceNode(std::string node_id,
                  const InferenceNetProperties &props,
                  Ax::Logger &logger,
                  std::chrono::milliseconds queue_timeout = std::chrono::milliseconds(2000),
                  std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> drop_sink = nullptr,
                  std::chrono::milliseconds join_timeout = std::chrono::milliseconds(5000),
                  size_t queue_depth = 1,
                  std::chrono::milliseconds done_callback_timeout = std::chrono::milliseconds(50));

    /** Stop the node; exceptions are swallowed. */
    ~InferenceNode() override;

    /**
     * Queue a frame for inference, dropping it if the input queue stays full.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame carrying a video buffer or a BGR image.
     */
    void process(std::shared_ptr<Frame> frame) override;
    /**
     * Stop the queues and threads and shut down the inference net.
     *
     * Each join waits at most join_timeout; a thread that does not exit in time is abandoned.
     */
    void stop() override;
    /**
     * Report the current fill level of the input and result queues.
     *
     * Returns:
     *   std::optional<QueueOccupancy>: Used and total depth of both queues.
     */
    std::optional<QueueOccupancy> queue_occupancy() const override;

private:
    /**
     * Log a dropped frame and, if a drop sink exists, mark the frame dropped and push it there.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): The dropped frame; may be null.
     *   reason (const std::string&): Short cause, e.g. "input_queue_ full".
     *   drop_timeout (std::chrono::milliseconds): Timeout reported in the log and used when
     *     pushing to the drop sink.
     */
    void report_drop(std::shared_ptr<Frame> frame, const std::string &reason,
        std::chrono::milliseconds drop_timeout);

    std::string node_id_;
    std::chrono::milliseconds queue_timeout_;
    std::chrono::milliseconds done_callback_timeout_;
    std::chrono::milliseconds join_timeout_;
    std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> drop_sink_;

    std::unique_ptr<BlockingQueue<std::shared_ptr<Frame>>> input_queue_;
    std::thread push_thread_;

    std::unique_ptr<BlockingQueue<std::shared_ptr<Frame>>> result_queue_;
    std::unique_ptr<InferenceNet> net_;
    std::thread drain_thread_;
};

}
