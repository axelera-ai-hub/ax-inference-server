
#pragma once

// Frame: the unit of work that flows through every pipeline node.

#include <chrono>
#include <memory>
#include <string>
#include <vector>

#include "AxInferenceNet.hpp"
#include "AxStreamerUtils.hpp"
#include "AxVideoBuffer.hpp"
#include "opencv2/opencv.hpp"
#include "pipeline/frame_flags.h"

namespace Ax {

/**
 * One image request travelling through the pipeline, with its decoded pixels, inference
 * metadata and drop state.
 *
 * Attributes:
 *     bgr: Decoded image in BGR order; ROI nodes temporarily replace it with a crop.
 *     video_buffer: Decoder output buffer; only meaningful when has_video_buffer() is true.
 *     meta: Inference results keyed by meta name.
 *     id: Request identifier assigned by the gRPC layer; used to match pending requests.
 *     is_dummy: Marks a filler frame rather than a real request; reset to false on reuse.
 *     encoded: Compressed request image bytes; released after decoding.
 *     net_idx: Index of the net replica handling the frame, -1 when unassigned.
 *     start_time: Set when the request is received.
 *     end_time: Set when the result is ready; used to compute latency.
 *     pipeline_ext: Per-frame state for ROI iteration (see FramePipelineExt).
 *     dropped: True if a node discarded the frame instead of processing it.
 *     drop_reason: Human-readable reason when dropped is true.
 *
 * Note:
 *     The gRPC FramePool reuses frames and resets meta, id, is_dummy, encoded, net_idx,
 *     timestamps, dropped and drop_reason on acquire.
 */
struct Frame {
    cv::Mat bgr;
    Ax::VideoBuffer video_buffer;
    Ax::MetaMap meta;
    int id = 0;
    bool is_dummy = false;
    std::shared_ptr<std::vector<uint8_t>> encoded;
    int net_idx = -1;
    std::chrono::high_resolution_clock::time_point start_time;
    std::chrono::high_resolution_clock::time_point end_time;

    std::shared_ptr<FramePipelineExt> pipeline_ext;

    bool dropped = false;
    std::string drop_reason;

    /** Check whether video_buffer holds a valid decoder buffer. */
    bool has_video_buffer() const { return video_buffer.is_valid(); }
};

}
