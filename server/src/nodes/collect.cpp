
// Implementation of RoiCollectNode (see nodes/collect.h).
#include "nodes/collect.h"

#include "AxMeta.hpp"
#include "AxMetaObjectDetection.hpp"

namespace Ax {

void RoiCollectNode::process(std::shared_ptr<Frame> frame)
{
    auto &ext = *frame->pipeline_ext;

    const int idx = ext.roi_index;
    for (const auto &cls_meta_key : cfg_.cls_meta_keys) {
        auto cls_it = frame->meta.find(cls_meta_key);
        if (cls_it == frame->meta.end()) continue;
        frame->meta[cls_meta_key + "_" + std::to_string(idx)] = std::move(cls_it->second);
        frame->meta.erase(cls_it);
    }
    ext.roi_index = idx + 1;

    auto det_it = frame->meta.find(cfg_.det_meta_key);
    auto *det = (det_it != frame->meta.end())
        ? dynamic_cast<AxMetaObjDetection *>(det_it->second.get())
        : nullptr;
    const size_t num_dets = det ? det->num_elements() : 0;

    if (static_cast<size_t>(ext.roi_index) >= num_dets) {
        frame->bgr = ext.roi_source_bgr;
        frame->meta["_roi_done"] = std::make_unique<AxMetaBase>();
    }

    if (next_) next_(frame);
}

}
