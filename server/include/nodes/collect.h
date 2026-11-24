
// Pipeline node that gathers per-ROI classifier results back onto the frame.
#pragma once

#include <string>
#include <vector>

#include "pipeline/node.h"

namespace Ax {

/**
 * Configuration for RoiCollectNode.
 *
 * Attributes:
 *   det_meta_key (std::string): Meta key of the detection result that defines the ROIs.
 *   cls_meta_keys (std::vector<std::string>): Meta keys of per-ROI results to rename with
 *     an ROI-index suffix.
 */
struct RoiCollectNodeConfig {
    std::string det_meta_key;
    std::vector<std::string> cls_meta_keys;
};

/**
 * Closes one iteration of an ROI loop started by RoiIterNode.
 *
 * Each pass renames the per-ROI result meta entries to "<key>_<roi_index>" so the next pass
 * does not overwrite them, then advances roi_index. After the last ROI it restores the
 * original full frame image and adds a "_roi_done" marker to the meta.
 */
class RoiCollectNode : public AxPipelineNode {
public:
    /**
     * Create the node.
     *
     * Args:
     *   cfg (RoiCollectNodeConfig): Node configuration.
     */
    explicit RoiCollectNode(RoiCollectNodeConfig cfg) : cfg_(std::move(cfg)) {}

    /**
     * Rename the current ROI's results, advance the ROI index, and forward the frame.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame with pipeline_ext set.
     */
    void process(std::shared_ptr<Frame> frame) override;

private:
    RoiCollectNodeConfig cfg_;
};

}
