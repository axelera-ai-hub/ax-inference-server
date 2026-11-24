#pragma once
#include "decoders/image_decoder.hpp"
#include "decoders/opencv_decoder.hpp"

#ifdef HAVE_TURBOJPEG
#include "decoders/simd_decoder.hpp"
#endif

/**
 * Chooses the ImageDecoder implementation for this build.
 *
 * With HAVE_TURBOJPEG defined it returns SIMDDecoder (TurboJPEG for JPEG, OpenCV fallback),
 * otherwise OpenCVDecoder.
 */
class DecoderFactory {
public:
    /**
     * Create a new decoder instance.
     *
     * Returns:
     *   std::unique_ptr<ImageDecoder>: SIMDDecoder or OpenCVDecoder, depending on the build.
     */
    static std::unique_ptr<ImageDecoder> create_decoder() {
        #ifdef HAVE_TURBOJPEG
        return std::make_unique<SIMDDecoder>();
        #else
        return std::make_unique<OpenCVDecoder>();
        #endif
    }

    /**
     * Describe the decoder configuration compiled into this build.
     *
     * Returns:
     *   std::string: A one-line description starting with "Image Decoder: ".
     */
    static std::string get_info() {
        std::string info = "Image Decoder: ";

        #ifdef HAVE_TURBOJPEG
        info += "TurboJPEG SIMD (JPEG) → OpenCV fallback (PNG/other)";
        #else
        info += "OpenCV only (no SIMD acceleration)";
        #endif

        return info;
    }
};
