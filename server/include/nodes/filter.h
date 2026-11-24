
// Pipeline node that filters detections in a meta entry by class, score and size.
#pragma once

#include <string>
#include <vector>

#include "pipeline/node.h"

namespace Ax {

/**
 * Configuration for FilterNode. A negative numeric value disables that criterion.
 *
 * Attributes:
 *   meta_key (std::string): Meta key of the detection result to filter.
 *   classes (std::vector<int>): Class ids to keep; empty keeps all classes.
 *   min_score (float): Minimum score to keep. Default -1 (disabled).
 *   max_score (float): Maximum score to keep. Default -1 (disabled).
 *   min_width (int): Minimum box width in pixels. Default -1 (disabled).
 *   min_height (int): Minimum box height in pixels. Default -1 (disabled).
 *   top_k (int): Keep at most this many highest-scoring detections. Default -1 (disabled).
 *   which (std::string): Reduction applied after the thresholds: "all" (keep every
 *     survivor), "highest_score" (keep the best one) or "center" (keep the one whose box
 *     centre is closest to the frame centre). Default "all".
 */
struct FilterNodeConfig {
    std::string meta_key;
    std::vector<int> classes;
    float min_score = -1.0f;
    float max_score = -1.0f;
    int min_width = -1;
    int min_height = -1;
    int top_k = -1;
    std::string which = "all";
};

/**
 * Removes detections from a meta entry that fail the configured criteria.
 *
 * Supports object, keypoint and segment detections; the result replaces the original meta
 * entry under the same key.
 */
class FilterNode : public AxPipelineNode {
public:
    /**
     * Create the node.
     *
     * Args:
     *   cfg (FilterNodeConfig): Node configuration.
     */
    explicit FilterNode(FilterNodeConfig cfg) : cfg_(std::move(cfg)) {}

    /**
     * Filter the detections under the configured meta key and forward the frame.
     *
     * If the key is missing or is not a detection type, an empty object detection is stored
     * under it instead.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame to filter in place.
     */
    void process(std::shared_ptr<Frame> frame) override;

private:
    FilterNodeConfig cfg_;
};

}
