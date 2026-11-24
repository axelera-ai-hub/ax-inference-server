
// Pipeline node that crops one detected region of interest per pass.
#pragma once

#include <string>

#include "pipeline/node.h"

namespace Ax {

/**
 * Configuration for RoiIterNode.
 *
 * Attributes:
 *   meta_key (std::string): Meta key of the object detection result that defines the ROIs.
 *   crop_padding (float): Padding added on each side of the box, as a fraction of the box
 *     width and height. Default 0.
 */
struct RoiIterNodeConfig {
    std::string meta_key;
    float crop_padding = 0.0f;
};

/**
 * Starts or continues an ROI loop by cropping the next detected box from the frame.
 *
 * The roi_index in the frame's pipeline_ext selects the box for each pass. Once all boxes
 * are consumed, or if there are none, the frame goes to the skip callback with its original
 * image restored.
 */
class RoiIterNode : public AxPipelineNode {
public:
    /**
     * Create the node.
     *
     * Args:
     *   cfg (RoiIterNodeConfig): Node configuration.
     */
    explicit RoiIterNode(RoiIterNodeConfig cfg) : cfg_(std::move(cfg)) {}

    /**
     * Crop the box at roi_index into frame->bgr and forward the frame.
     *
     * Saves a copy of the full image on the first pass, clamps the padded box to the image, and
     * records the crop rectangle in roi_crop_rects. With no boxes left, calls the skip callback
     * instead.
     *
     * Args:
     *   frame (std::shared_ptr<Frame>): Frame with pipeline_ext set.
     */
    void process(std::shared_ptr<Frame> frame) override;

    /** Set the successor for frames with no ROI left to process. */
    void set_skip(PipelineCallback cb) { skip_ = std::move(cb); }

private:
    RoiIterNodeConfig cfg_;
    PipelineCallback skip_;
};

}
