
// Implementation of LoopGuardNode (see nodes/guard.h).
#include "nodes/guard.h"

#include "common/io_uring_logger.hpp"
#include "pipeline/join_with_timeout.h"
#include "pipeline/timed_queue_push.h"

namespace Ax {

LoopGuardNode::LoopGuardNode(LoopGuardNodeConfig cfg)
    : cfg_(std::move(cfg))
    , dispatch_queue_(std::make_unique<BlockingQueue<std::shared_ptr<Frame>>>(
          cfg_.dispatch_queue_depth))
{
    dispatch_thread_ = std::thread([this]() {
        while (true) {
            auto frame = dispatch_queue_->wait_one();
            if (!frame) break;

            auto &ext = *frame->pipeline_ext;
            const bool predicate_done = cfg_.until && cfg_.until->eval(*frame);
            const bool cap_hit = ext.roi_index >= cfg_.max_iters;

            if (predicate_done || cap_hit) {
                if (exit_cb_) exit_cb_(frame);
            } else {
                if (continue_cb_) continue_cb_(frame);
            }
        }
    });
}

LoopGuardNode::~LoopGuardNode()
{
    try { stop(); } catch (...) {}
}

void LoopGuardNode::process(std::shared_ptr<Frame> frame)
{
    if (!try_push_for(*dispatch_queue_, frame, cfg_.queue_timeout)) {
        auto frame_id = frame ? frame->id : -1;
        IoUringLogger::instance().logf("PIPELINE",
            "LoopGuardNode: dispatch_queue_ full after %ldms, dropping frame %d\n",
            static_cast<long>(cfg_.queue_timeout.count()), frame_id);
    }
}

void LoopGuardNode::stop()
{
    dispatch_queue_->stop();
    join_with_timeout(dispatch_thread_, std::chrono::milliseconds(5000),
        "LoopGuardNode dispatch_thread_");
}

}
