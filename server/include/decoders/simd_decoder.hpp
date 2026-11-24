#pragma once
#include "decoders/image_decoder.hpp"
#include "decoders/format_detection.hpp"
#include "decoders/opencv_decoder.hpp"

#ifdef HAVE_TURBOJPEG
#include "decoders/turbojpeg_decoder.hpp"
#endif

/**
 * Decoder that prefers TurboJPEG for JPEG input and falls back to OpenCV otherwise.
 *
 * The format is auto-detected with FormatDetection when the caller passes UNKNOWN. If
 * TurboJPEG is not compiled in (HAVE_TURBOJPEG undefined) or fails to initialise, or the
 * JPEG decode fails, the request is served by OpenCVDecoder.
 *
 * Note:
 *   Each instance owns a TurboJPEG handle, so do not share one instance between threads;
 *   the server creates one decoder per decode worker.
 */
class SIMDDecoder : public ImageDecoder {
public:
    /**
     * Create the TurboJPEG decoder (when compiled in) and the OpenCV fallback.
     *
     * A failure to construct the TurboJPEG decoder is swallowed and leaves only the fallback.
     */
    SIMDDecoder() {
        #ifdef HAVE_TURBOJPEG
        try {
            jpeg_decoder_ = std::make_unique<TurboJPEGDecoder>();
        } catch (const std::exception& e) {
            jpeg_decoder_ = nullptr;
        }
        #endif

        opencv_fallback_ = std::make_unique<OpenCVDecoder>();
    }

    /**
     * Decode to BGR, using TurboJPEG for JPEG input and OpenCV otherwise.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   bgr_out (cv::Mat&): Receives the decoded BGR image.
     *   format (ImageFormat, optional): Input format hint; detected when UNKNOWN.
     *
     * Returns:
     *   bool: True on success.
     */
    bool decode(const std::vector<uint8_t>& encoded,
                cv::Mat& bgr_out,
                ImageFormat format = ImageFormat::UNKNOWN) override {
        if (format == ImageFormat::UNKNOWN) {
            format = FormatDetection::detect(encoded);
        }

        if (format == ImageFormat::JPEG && jpeg_decoder_) {
            if (jpeg_decoder_->decode(encoded, bgr_out, format)) {
                return true;
            }
        }

        return opencv_fallback_->decode(encoded, bgr_out, format);
    }

    /**
     * Decode to BGR or I420, using TurboJPEG for JPEG input and OpenCV otherwise.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (cv::Mat&): Receives the decoded image.
     *   input_format (ImageFormat, optional): Input format hint; detected when UNKNOWN.
     *   output_format (ImageFormat, optional): BGR or I420. Defaults to BGR.
     *
     * Returns:
     *   bool: True on success.
     */
    bool decode_ex(const std::vector<uint8_t>& encoded,
                    cv::Mat& output,
                    ImageFormat input_format = ImageFormat::UNKNOWN,
                    ImageFormat output_format = ImageFormat::BGR) override {

        if (input_format == ImageFormat::UNKNOWN) {
            input_format = FormatDetection::detect(encoded);
        }

        if (input_format == ImageFormat::JPEG && jpeg_decoder_) {
            if (jpeg_decoder_->decode_ex(encoded, output, input_format, output_format)) {
                return true;
            }
        }

        return opencv_fallback_->decode_ex(encoded, output, input_format, output_format);
    }

    /**
     * Decode to I420 into an Ax::VideoBuffer, using TurboJPEG for JPEG input and OpenCV otherwise.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (Ax::VideoBuffer&): Destination buffer.
     *   input_format (ImageFormat, optional): Input format hint; detected when UNKNOWN.
     *   output_format (ImageFormat, optional): Requested output format. Defaults to I420.
     *
     * Returns:
     *   bool: True on success.
     */
    bool decode_to_videobuffer(const std::vector<uint8_t>& encoded,
                               Ax::VideoBuffer& output,
                               ImageFormat input_format = ImageFormat::UNKNOWN,
                               ImageFormat output_format = ImageFormat::I420) override {
        if (input_format == ImageFormat::UNKNOWN) {
            input_format = FormatDetection::detect(encoded);
        }
        if (input_format == ImageFormat::JPEG && jpeg_decoder_) {
            if (jpeg_decoder_->decode_to_videobuffer(encoded, output, input_format, output_format)) {
                return true;
            }
        }
        return opencv_fallback_->decode_to_videobuffer(encoded, output, input_format, output_format);
    }

    /** Return "SIMDDecoder". */
    const char* name() const override {
        return "SIMDDecoder";
    }

private:
    // Null when TurboJPEG is unavailable or failed to initialise.
    std::unique_ptr<ImageDecoder> jpeg_decoder_;
    std::unique_ptr<ImageDecoder> opencv_fallback_;
};
