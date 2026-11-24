
// Implementation of InferenceNode (see nodes/inference.h).
#include "nodes/inference.h"

#include "AxUtils.hpp"
#include "common/io_uring_logger.hpp"
#include "pipeline/join_with_timeout.h"
#include "pipeline/timed_queue_push.h"

namespace Ax {

InferenceNode::InferenceNode(std::string node_id,
                             const InferenceNetProperties &props,
                             Ax::Logger &logger,
                             std::chrono::milliseconds queue_timeout,
                             std::shared_ptr<BlockingQueue<std::shared_ptr<Frame>>> drop_sink,
                             std::chrono::milliseconds join_timeout,
                             size_t queue_depth,
                             std::chrono::milliseconds done_callback_timeout)
    : node_id_(std::move(node_id))
    , queue_timeout_(queue_timeout)
    , done_callback_timeout_(done_callback_timeout)
    , join_timeout_(join_timeout)
    , drop_sink_(std::move(drop_sink))
    , input_queue_(std::make_unique<BlockingQueue<std::shared_ptr<Frame>>>(queue_depth))
    , result_queue_(std::make_unique<BlockingQueue<std::shared_ptr<Frame>>>(queue_depth))
{
    net_ = Ax::create_inference_net(props, logger,
        // Completion callback of the inference net; runs on the net's thread.
        [this](CompletedFrame &done) {
            if (done.end_of_input) {
                result_queue_->stop();
                return;
            }
            // Take ownership of the Frame the net carried through as an opaque buffer handle.
            auto raw = std::exchange(done.buffer_handle, {});
            auto frame = std::static_pointer_cast<Frame>(raw);
            if (!try_push_for(*result_queue_, frame, done_callback_timeout_)) {
                report_drop(std::move(frame), "result_queue_ full", done_callback_timeout_);
            }
        }, {}, nullptr);

    push_thread_ = std::thread([this]() {
        while (true) {
            auto frame = input_queue_->wait_one();
            if (!frame) break;

            AxVideoInterface video;
            if (frame->has_video_buffer()) {
                video = frame->video_buffer.to_video_interface();
            } else if (!frame->bgr.empty()) {
                video = Ax::video_from_cvmat(frame->bgr, AxVideoFormat::BGR);
            } else {
                // A frame with neither a video buffer nor a BGR image has nothing to infer on and is skipped without a report.
                continue;
            }
            net_->push_new_frame(frame, video, frame->meta, frame->id);
        }
    });

    drain_thread_ = std::thread([this]() {
        while (true) {
            auto frame = result_queue_->wait_one();
            if (!frame) break;
            if (next_) next_(frame);
        }
    });
}

InferenceNode::~InferenceNode()
{
    try { stop(); } catch (...) {}
}

void InferenceNode::process(std::shared_ptr<Frame> frame)
{
    if (!try_push_for(*input_queue_, frame, queue_timeout_)) {
        report_drop(std::move(frame), "input_queue_ full", queue_timeout_);
    }
}

void InferenceNode::report_drop(std::shared_ptr<Frame> frame, const std::string &reason,
    std::chrono::milliseconds drop_timeout)
{
    auto frame_id = frame ? frame->id : -1;
    IoUringLogger::instance().logf("PIPELINE",
        "InferenceNode[%s]: %s after %ldms, dropping frame %d\n",
        node_id_.c_str(), reason.c_str(), static_cast<long>(drop_timeout.count()), frame_id);

    if (!frame || !drop_sink_) return;

    frame->dropped = true;
    frame->drop_reason = "InferenceNode[" + node_id_ + "]: " + reason;
    if (!try_push_for(*drop_sink_, frame, drop_timeout)) {
        IoUringLogger::instance().logf("PIPELINE",
            "InferenceNode[%s]: could not report drop of frame %d to client "
            "(result queue also full) — client will see the pipeline timeout instead\n",
            node_id_.c_str(), frame_id);
    }
}

void InferenceNode::stop()
{
    input_queue_->stop();
    join_with_timeout(push_thread_, join_timeout_, node_id_ + " push_thread_");

    if (net_) {
        std::thread stop_thread([this]() { net_->stop(); });
        join_with_timeout(stop_thread, join_timeout_, node_id_ + " net_->stop()");
    }

    result_queue_->stop();
    join_with_timeout(drain_thread_, join_timeout_, node_id_ + " drain_thread_");
}

std::optional<AxPipelineNode::QueueOccupancy> InferenceNode::queue_occupancy() const
{
    AxPipelineNode::QueueOccupancy occ;
    occ.node_id = node_id_;
    {
        std::lock_guard<std::mutex> lk(input_queue_->mutex);
        occ.input_used = input_queue_->queue.size();
        occ.input_depth = input_queue_->queue_depth;
    }
    {
        std::lock_guard<std::mutex> lk(result_queue_->mutex);
        occ.result_used = result_queue_->queue.size();
        occ.result_depth = result_queue_->queue_depth;
    }
    return occ;
}

}
