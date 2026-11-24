
// Implementation of RoiIterNode (see nodes/iter.h).
#include "nodes/iter.h"

#include <algorithm>

#include "AxMetaObjectDetection.hpp"

namespace Ax {

void RoiIterNode::process(std::shared_ptr<Frame> frame)
{
    auto &ext = *frame->pipeline_ext;

    if (ext.roi_index == 0) {
        ext.roi_source_bgr = frame->bgr.clone();
    }

    // Detection count is 0 when the key is missing or holds a different meta type.
    auto it = frame->meta.find(cfg_.meta_key);
    auto *det = (it != frame->meta.end())
        ? dynamic_cast<AxMetaObjDetection *>(it->second.get())
        : nullptr;
    const size_t num_dets = det ? det->num_elements() : 0;

    if (num_dets == 0 || static_cast<size_t>(ext.roi_index) >= num_dets) {
        frame->bgr = ext.roi_source_bgr;
        if (skip_) skip_(frame);
        return;
    }

    const auto box = det->get_box_xyxy(static_cast<size_t>(ext.roi_index));
    const int bw = box.x2 - box.x1;
    const int bh = box.y2 - box.y1;
    const int pad_x = static_cast<int>(bw * cfg_.crop_padding);
    const int pad_y = static_cast<int>(bh * cfg_.crop_padding);

    const int src_w = ext.roi_source_bgr.cols;
    const int src_h = ext.roi_source_bgr.rows;
    // Clamp so the padded crop stays inside the source image and is at least 1 pixel wide and high.
    const int x1 = std::clamp(box.x1 - pad_x, 0, src_w - 1);
    const int y1 = std::clamp(box.y1 - pad_y, 0, src_h - 1);
    const int x2 = std::clamp(box.x2 + pad_x, x1 + 1, src_w);
    const int y2 = std::clamp(box.y2 + pad_y, y1 + 1, src_h);
    const cv::Rect rect(x1, y1, x2 - x1, y2 - y1);

    frame->bgr = ext.roi_source_bgr(rect).clone();
    ext.roi_crop_rects[ext.roi_index] = rect;

    if (next_) next_(frame);
}

}
