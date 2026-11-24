#pragma once
#include <opencv2/opencv.hpp>
#include <vector>
#include <memory>
#include <string>
#include <optional>
#include "AxVideoBuffer.hpp"

/**
 * Pixel or container formats used by the decoder interface.
 *
 * JPEG, PNG and UNKNOWN describe encoded input (UNKNOWN requests auto-detection).
 * BGR and I420 describe decoded output.
 */
enum class ImageFormat {
    JPEG,
    PNG,
    UNKNOWN,

    BGR,
    I420
};

/**
 * Abstract interface for decoding an encoded image into raw pixels.
 *
 * Implementations are OpenCVDecoder, TurboJPEGDecoder and SIMDDecoder. Only decode() and
 * name() are mandatory; decode_ex() and decode_to_videobuffer() have defaults that report
 * unsupported conversions.
 */
class ImageDecoder {
public:
    virtual ~ImageDecoder() = default;

    /**
     * Decode an encoded image to a BGR cv::Mat.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   bgr_out (cv::Mat&): Receives the decoded 8-bit, 3-channel BGR image.
     *   format (ImageFormat, optional): Input format hint. Defaults to UNKNOWN.
     *
     * Returns:
     *   bool: True on success, false if the image could not be decoded.
     */
    virtual bool decode(const std::vector<uint8_t>& encoded,
                        cv::Mat& bgr_out,
                        ImageFormat format = ImageFormat::UNKNOWN) = 0;

    /**
     * Decode an encoded image to the requested output format in a cv::Mat.
     *
     * The default implementation supports only BGR output (delegating to decode()).
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (cv::Mat&): Receives the decoded image. For I420 it is a single-channel Mat
     *     with height * 3 / 2 rows.
     *   input_format (ImageFormat, optional): Input format hint. Defaults to UNKNOWN.
     *   output_format (ImageFormat, optional): Requested output format. Defaults to BGR.
     *
     * Returns:
     *   bool: True on success, false on decode failure or unsupported output format.
     */
    virtual bool decode_ex(const std::vector<uint8_t>& encoded,
                          cv::Mat& output,
                          ImageFormat input_format = ImageFormat::UNKNOWN,
                          ImageFormat output_format = ImageFormat::BGR) {
        if (output_format == ImageFormat::BGR) {
            return decode(encoded, output, input_format);
        }
        return false;
    }

    /**
     * Decode an encoded image directly into an Ax::VideoBuffer.
     *
     * The default implementation does nothing and returns false.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): Compressed image bytes.
     *   output (Ax::VideoBuffer&): Destination buffer, reallocated by implementations when its
     *     size or format does not match.
     *   input_format (ImageFormat, optional): Input format hint. Defaults to UNKNOWN.
     *   output_format (ImageFormat, optional): Requested output format. Defaults to I420.
     *
     * Returns:
     *   bool: True on success, false if unsupported or decoding failed.
     */
    virtual bool decode_to_videobuffer(const std::vector<uint8_t>& encoded,
                                       Ax::VideoBuffer& output,
                                       ImageFormat input_format = ImageFormat::UNKNOWN,
                                       ImageFormat output_format = ImageFormat::I420)
    {
        return false;
    }

    /** Return a short human-readable decoder name used in log messages. */
    virtual const char* name() const = 0;
};
