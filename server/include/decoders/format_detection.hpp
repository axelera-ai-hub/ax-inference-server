#pragma once
#include "decoders/image_decoder.hpp"

/**
 * Detects the encoded image format from its leading bytes.
 *
 * Only JPEG is recognised; every other input, including PNG, is reported as UNKNOWN.
 */
class FormatDetection {
public:
    /**
     * Identify the image format from the magic bytes.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *
     * Returns:
     *   ImageFormat: JPEG if the data starts with FF D8 FF, otherwise UNKNOWN (also when fewer
     *     than 3 bytes are given).
     */
    static ImageFormat detect(const std::vector<uint8_t>& encoded) {
        if (encoded.size() < 3) {
            return ImageFormat::UNKNOWN;
        }

        if (encoded[0] == 0xFF && encoded[1] == 0xD8 && encoded[2] == 0xFF) {
            return ImageFormat::JPEG;
        }

        return ImageFormat::UNKNOWN;
    }
};
