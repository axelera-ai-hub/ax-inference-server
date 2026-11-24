
// Implementation of FilterNode (see nodes/filter.h) and its helpers.
#include "nodes/filter.h"

#include <algorithm>
#include <limits>
#include <numeric>

#include "AxMetaKptsDetection.hpp"
#include "AxMetaObjectDetection.hpp"
#include "AxMetaSegmentsDetection.hpp"

namespace Ax {

// Helpers that select surviving detections and rebuild each meta type from them.
namespace {

/**
 * Pick the detection indices that satisfy a filter configuration.
 *
 * Applies, in order, the class list and score/size thresholds, then the "which" reduction
 * ("highest_score" or "center"), then the top_k limit. "center" is skipped when the frame
 * image is empty. The top_k step sorts the survivors by descending score.
 *
 * Args:
 *   bbox (const AxMetaBbox&): Detections to evaluate.
 *   cfg (const FilterNodeConfig&): Filter criteria.
 *   frame_bgr (const cv::Mat&): Frame image, used only for its size by "center".
 *
 * Returns:
 *   std::vector<size_t>: Indices into bbox to keep.
 */
std::vector<size_t> select_surviving_indices(
    const AxMetaBbox &bbox, const FilterNodeConfig &cfg, const cv::Mat &frame_bgr)
{
    std::vector<size_t> surviving;
    for (size_t i = 0; i < bbox.num_elements(); ++i) {
        const int cls = bbox.class_id(i);
        const float sc = bbox.score(i);
        const auto box = bbox.get_box_xyxy(i);
        const int w = box.x2 - box.x1;
        const int h = box.y2 - box.y1;

        if (!cfg.classes.empty()
            && std::find(cfg.classes.begin(), cfg.classes.end(), cls)
                == cfg.classes.end())
            continue;
        if (cfg.min_score >= 0.0f && sc < cfg.min_score) continue;
        if (cfg.max_score >= 0.0f && sc > cfg.max_score) continue;
        if (cfg.min_width  >= 0   && w  < cfg.min_width)  continue;
        if (cfg.min_height >= 0   && h  < cfg.min_height) continue;

        surviving.push_back(i);
    }

    if (cfg.which == "highest_score" && !surviving.empty()) {
        size_t best = surviving[0];
        for (size_t i : surviving)
            if (bbox.score(i) > bbox.score(best)) best = i;
        surviving = { best };
    } else if (cfg.which == "center" && !surviving.empty() && !frame_bgr.empty()) {
        const float cx = frame_bgr.cols / 2.0f;
        const float cy = frame_bgr.rows / 2.0f;
        size_t best = surviving[0];
        float best_d = std::numeric_limits<float>::max();
        for (size_t i : surviving) {
            const auto box = bbox.get_box_xyxy(i);
            const float bx = (box.x1 + box.x2) / 2.0f;
            const float by = (box.y1 + box.y2) / 2.0f;
            const float d = (bx - cx) * (bx - cx) + (by - cy) * (by - cy);
            if (d < best_d) { best_d = d; best = i; }
        }
        surviving = { best };
    }

    if (cfg.top_k >= 0 && static_cast<int>(surviving.size()) > cfg.top_k) {
        std::sort(surviving.begin(), surviving.end(),
            [&](size_t a, size_t b) { return bbox.score(a) > bbox.score(b); });
        surviving.resize(static_cast<size_t>(cfg.top_k));
    }

    return surviving;
}

/**
 * Build a new object detection meta containing only the given detections.
 *
 * Args:
 *   src (const AxMetaObjDetection&): Source detections.
 *   keep (const std::vector<size_t>&): Indices to copy.
 *
 * Returns:
 *   std::unique_ptr<AxMetaBase>: New meta with boxes, scores and class ids of the kept entries.
 */
std::unique_ptr<AxMetaBase> rebuild_obj_detection(
    const AxMetaObjDetection &src, const std::vector<size_t> &keep)
{
    std::vector<box_xyxy> boxes;
    std::vector<float> scores;
    std::vector<int> classes;
    boxes.reserve(keep.size());
    scores.reserve(keep.size());
    classes.reserve(keep.size());
    for (size_t i : keep) {
        boxes.push_back(src.get_box_xyxy(i));
        scores.push_back(src.score(i));
        classes.push_back(src.class_id(i));
    }
    return std::make_unique<AxMetaObjDetection>(
        std::move(boxes), std::move(scores), std::move(classes));
}

/**
 * Build a new keypoint detection meta containing only the given detections.
 *
 * The keypoint count per detection is taken from the source shape, defaulting to 17 when the
 * shape is empty.
 *
 * Args:
 *   src (const AxMetaKptsDetection&): Source detections.
 *   keep (const std::vector<size_t>&): Indices to copy.
 *
 * Returns:
 *   std::unique_ptr<AxMetaBase>: New meta with boxes, keypoints and scores of the kept entries.
 */
std::unique_ptr<AxMetaBase> rebuild_kpts_detection(
    const AxMetaKptsDetection &src, const std::vector<size_t> &keep)
{
    const auto kshape = src.get_kpts_shape();
    const size_t n_kpts = kshape.empty() ? 17u : static_cast<size_t>(kshape[0]);

    std::vector<box_xyxy> boxes;
    std::vector<float> scores;
    KptXyvVector kpts;
    boxes.reserve(keep.size());
    scores.reserve(keep.size());
    kpts.reserve(keep.size() * n_kpts);
    for (size_t i : keep) {
        boxes.push_back(src.get_box_xyxy(i));
        scores.push_back(src.score(i));
        if (n_kpts > 0) {
            for (const auto &kpt : src.get_kpts_xyv(i, n_kpts))
                kpts.push_back(kpt);
        }
    }
    return std::make_unique<AxMetaKptsDetection>(std::move(boxes), std::move(kpts),
        std::move(scores), std::vector<int>{}, kshape, src.get_decoder_name());
}

/**
 * Build a new segment detection meta containing only the given detections.
 *
 * Args:
 *   src (const AxMetaSegmentsDetection&): Source detections.
 *   keep (const std::vector<size_t>&): Indices to copy.
 *
 * Returns:
 *   std::unique_ptr<AxMetaBase>: New meta with boxes, segments, scores and class ids of the
 *     kept entries, reusing the source segment shape and decoder name.
 */
std::unique_ptr<AxMetaBase> rebuild_segments_detection(
    const AxMetaSegmentsDetection &src, const std::vector<size_t> &keep)
{
    std::vector<box_xyxy> boxes;
    std::vector<float> scores;
    std::vector<int> classes;
    std::vector<Segment> segments;
    boxes.reserve(keep.size());
    scores.reserve(keep.size());
    classes.reserve(keep.size());
    segments.reserve(keep.size());
    for (size_t i : keep) {
        boxes.push_back(src.get_box_xyxy(i));
        scores.push_back(src.score(i));
        classes.push_back(src.class_id(i));
        segments.push_back(src.get_segment(i));
    }
    const auto &shape = src.get_segments_shape();
    const SegmentShape seg_shape{ shape.size() > 2 ? shape[2] : 0,
        shape.size() > 1 ? shape[1] : 0 };
    return std::make_unique<AxMetaSegmentsDetection>(std::move(boxes), std::move(segments),
        std::move(scores), std::move(classes), std::vector<int>{}, seg_shape,
        src.get_decoder_name());
}

}

void FilterNode::process(std::shared_ptr<Frame> frame)
{
    auto it = frame->meta.find(cfg_.meta_key);
    auto *bbox = (it != frame->meta.end())
        ? dynamic_cast<AxMetaBbox *>(it->second.get())
        : nullptr;

    if (!bbox) {
        frame->meta[cfg_.meta_key] = std::make_unique<AxMetaObjDetection>();
        if (next_) next_(frame);
        return;
    }

    const auto keep = select_surviving_indices(*bbox, cfg_, frame->bgr);

    if (auto *kd = dynamic_cast<AxMetaKptsDetection *>(it->second.get())) {
        frame->meta[cfg_.meta_key] = rebuild_kpts_detection(*kd, keep);
    } else if (auto *sd = dynamic_cast<AxMetaSegmentsDetection *>(it->second.get())) {
        frame->meta[cfg_.meta_key] = rebuild_segments_detection(*sd, keep);
    } else if (auto *od = dynamic_cast<AxMetaObjDetection *>(it->second.get())) {
        frame->meta[cfg_.meta_key] = rebuild_obj_detection(*od, keep);
    }

    if (next_) next_(frame);
}

}
