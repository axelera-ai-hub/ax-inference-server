
#pragma once

// Per-frame state shared by the ROI iteration nodes.
#include <unordered_map>
#include "opencv2/opencv.hpp"

namespace Ax {

/**
 * Bookkeeping for iterating over detected regions of interest (ROIs) in one frame.
 *
 * Attributes:
 *     roi_crop_rects: Crop rectangle used for each ROI, keyed by ROI index.
 *     roi_source_bgr: Full-size copy of the image, kept while frame->bgr holds a crop.
 *     roi_index: Index of the ROI currently being processed.
 */
struct FramePipelineExt {
    std::unordered_map<int, cv::Rect> roi_crop_rects;

    cv::Mat roi_source_bgr;

    int roi_index = 0;
};

}
