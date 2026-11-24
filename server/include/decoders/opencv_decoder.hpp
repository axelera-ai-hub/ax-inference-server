#pragma once
#include "decoders/image_decoder.hpp"

/**
 * ImageDecoder backed by cv::imdecode.
 *
 * Handles any format OpenCV supports and serves as the fallback decoder for SIMDDecoder.
 */
class OpenCVDecoder : public ImageDecoder {
public:
    OpenCVDecoder() = default;

    /**
     * Decode an encoded image to BGR with cv::imdecode.
     *
     * The input is wrapped in a thread-local cv::Mat header without copying. The format hint is
     * ignored because OpenCV detects the format itself.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   bgr_out (cv::Mat&): Receives the decoded BGR image.
     *   format (ImageFormat, optional): Unused.
     *
     * Returns:
     *   bool: True if the decoded image is non-empty.
     */
    bool decode(const std::vector<uint8_t>& encoded,
                cv::Mat& bgr_out,
                ImageFormat format = ImageFormat::UNKNOWN) override {
        thread_local cv::Mat raw_wrapper;
        raw_wrapper = cv::Mat(1, encoded.size(), CV_8UC1,
                              const_cast<uint8_t*>(encoded.data()));

        bgr_out = cv::imdecode(raw_wrapper, cv::IMREAD_COLOR);
        return !bgr_out.empty();
    }

    /**
     * Decode to BGR or to I420 (converted from BGR with cv::cvtColor).
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (cv::Mat&): Receives the BGR image, or a single-channel I420 Mat with
     *     height * 3 / 2 rows.
     *   input_format (ImageFormat, optional): Passed through to decode(). Defaults to UNKNOWN.
     *   output_format (ImageFormat, optional): BGR or I420. Defaults to BGR.
     *
     * Returns:
     *   bool: True on success, false on decode failure or any other output format.
     */
    bool decode_ex(const std::vector<uint8_t>& encoded,
                    cv::Mat& output,
                    ImageFormat input_format = ImageFormat::UNKNOWN,
                    ImageFormat output_format = ImageFormat::BGR) override {

        cv::Mat bgr;
        if (!decode(encoded, bgr, input_format)) {
            return false;
        }

        if (output_format == ImageFormat::BGR) {
            output = std::move(bgr);
            return true;
        }

        if (output_format == ImageFormat::I420) {
            cv::cvtColor(bgr, output, cv::COLOR_BGR2YUV_I420);
            return true;
        }

        return false;
    }

    /**
     * Decode to I420 and copy the result into an Ax::VideoBuffer.
     *
     * The buffer is reallocated if it is invalid or its size or format differs from the image.
     * The copy assumes output.size() equals the packed I420 size of the decoded image.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (Ax::VideoBuffer&): Destination buffer.
     *   input_format (ImageFormat, optional): Passed through to decode(). Defaults to UNKNOWN.
     *   output_format (ImageFormat, optional): Must be I420. Defaults to I420.
     *
     * Returns:
     *   bool: True on success, false on decode failure, allocation failure, or a non-I420
     *     output format.
     */
    bool decode_to_videobuffer(const std::vector<uint8_t>& encoded,
                               Ax::VideoBuffer& output,
                               ImageFormat input_format = ImageFormat::UNKNOWN,
                               ImageFormat output_format = ImageFormat::I420) override {
        if (output_format != ImageFormat::I420) return false;

        cv::Mat bgr;
        if (!decode(encoded, bgr, input_format)) return false;

        int width = bgr.cols;
        int height = bgr.rows;

        if (!output.is_valid() || output.width() != width ||
            output.height() != height || output.format() != AxVideoFormat::I420) {
            try {
                output = Ax::VideoBuffer(width, height, AxVideoFormat::I420);
            } catch (...) { return false; }
        }

        cv::Mat yuv;
        cv::cvtColor(bgr, yuv, cv::COLOR_BGR2YUV_I420);
        std::memcpy(output.data(), yuv.data, output.size());
        return true;
    }

    /** Return "OpenCVDecoder". */
    const char* name() const override {
        return "OpenCVDecoder";
    }
};
