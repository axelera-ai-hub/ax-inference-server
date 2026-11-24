#pragma once
#include "decoders/image_decoder.hpp"

#ifdef HAVE_TURBOJPEG
#include <turbojpeg.h>
#include <stdexcept>

/**
 * JPEG-only ImageDecoder backed by libjpeg-turbo (TurboJPEG API).
 *
 * Decodes with TJFLAG_FASTDCT (and fast upsampling for BGR), trading a little accuracy for
 * speed. PNG input is rejected. Compiled only when HAVE_TURBOJPEG is defined.
 *
 * Note:
 *   Owns a tjhandle, so it is non-copyable and must not be used from several threads at
 *   once.
 */
class TurboJPEGDecoder : public ImageDecoder {
public:
    /**
     * Create the TurboJPEG decompressor handle.
     *
     * Raises:
     *   std::runtime_error: If tjInitDecompress fails.
     */
    TurboJPEGDecoder() {
        tj_handle_ = tjInitDecompress();
        if (!tj_handle_) {
            throw std::runtime_error("tjInitDecompress failed");
        }
    }

    /** Destroy the TurboJPEG handle. */
    ~TurboJPEGDecoder() override {
        if (tj_handle_) {
            tjDestroy(tj_handle_);
        }
    }

    TurboJPEGDecoder(const TurboJPEGDecoder&) = delete;
    TurboJPEGDecoder& operator=(const TurboJPEGDecoder&) = delete;

    /**
     * Decode a JPEG to BGR.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): JPEG bytes.
     *   bgr_out (cv::Mat&): Receives the decoded 8-bit, 3-channel BGR image.
     *   format (ImageFormat, optional): Returns false immediately if PNG. Defaults to UNKNOWN.
     *
     * Returns:
     *   bool: True on success, false if the header or the decompression fails.
     */
    bool decode(const std::vector<uint8_t>& encoded,
                cv::Mat& bgr_out,
                ImageFormat format = ImageFormat::UNKNOWN) override {
        if (format == ImageFormat::PNG) {
            return false;
        }

        int width, height, subsamp, colorspace;

        if (tjDecompressHeader3(tj_handle_,
                                encoded.data(),
                                encoded.size(),
                                &width, &height,
                                &subsamp,
                                &colorspace) != 0) {
            return false;
        }

        bgr_out.create(height, width, CV_8UC3);

        if (tjDecompress2(tj_handle_,
                          encoded.data(),
                          encoded.size(),
                          bgr_out.data,
                          width,
                          0,
                          height,
                          TJPF_BGR,
                          TJFLAG_FASTDCT | TJFLAG_FASTUPSAMPLE) != 0) {
            return false;
        }

        return true;
    }

    /**
     * Decode a JPEG to BGR or I420.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): JPEG bytes.
     *   output (cv::Mat&): Receives the image. For I420 it is a single-channel Mat with
     *     height + height / 2 rows.
     *   input_format (ImageFormat, optional): Returns false immediately if PNG.
     *   output_format (ImageFormat, optional): BGR or I420. Defaults to BGR.
     *
     * Returns:
     *   bool: True on success, false on failure or any other output format.
     */
    bool decode_ex(const std::vector<uint8_t>& encoded,
                    cv::Mat& output,
                    ImageFormat input_format = ImageFormat::UNKNOWN,
                    ImageFormat output_format = ImageFormat::BGR) override {

        if (input_format == ImageFormat::PNG) {
            return false;
        }

        int width, height, subsamp, colorspace;
        if (tjDecompressHeader3(tj_handle_, encoded.data(), encoded.size(),
                                &width, &height, &subsamp, &colorspace) != 0) {
            return false;
        }

        if (output_format == ImageFormat::I420) {
            return decode_to_i420(encoded, output, width, height);
        }

        if (output_format == ImageFormat::BGR) {
            return decode(encoded, output, input_format);
        }

        return false;
    }

    /** Return "TurboJPEGDecoder". */
    const char* name() const override {
        return "TurboJPEGDecoder";
    }

private:
    // Decompressor handle owned by this object.
    tjhandle tj_handle_ = nullptr;

    /**
     * Decompress a JPEG into a planar YUV Mat.
     *
     * The Mat is sized for 4:2:0 (height + height / 2 rows) and filled by tjDecompressToYUV2 with
     * 1-byte row alignment, so the plane layout follows the JPEG's own chroma subsampling.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): JPEG bytes.
     *   output (cv::Mat&): Destination, re-created if its shape or type differs.
     *   width (int): Image width in pixels, from the JPEG header.
     *   height (int): Image height in pixels, from the JPEG header.
     *
     * Returns:
     *   bool: True on success.
     */
    bool decode_to_i420(const std::vector<uint8_t>& encoded,
                        cv::Mat& output,
                        int width, int height)
    {
        const int rows = height + (height >> 1);

        if (output.rows != rows || output.cols != width || output.type() != CV_8UC1) {
            output.create(rows, width, CV_8UC1);
        }

        return tjDecompressToYUV2(
            tj_handle_,
            encoded.data(),
            encoded.size(),
            output.data,
            width,
            1,
            height,
            TJFLAG_FASTDCT
        ) == 0;
    }

    /**
     * Decompress a JPEG to I420 directly into an Ax::VideoBuffer.
     *
     * The buffer is reallocated if it is invalid or its size or format differs from the image.
     * Declared private in this class but reachable through the ImageDecoder interface.
     *
     * Args:
     *   encoded (const std::vector<uint8_t>&): JPEG bytes.
     *   output (Ax::VideoBuffer&): Destination buffer.
     *   input_format (ImageFormat, optional): Returns false immediately if PNG.
     *   output_format (ImageFormat, optional): Must be I420. Defaults to I420.
     *
     * Returns:
     *   bool: True on success, false on failure, allocation error, or a non-I420 output format.
     */
    bool decode_to_videobuffer(const std::vector<uint8_t>& encoded,
                                Ax::VideoBuffer& output,
                                ImageFormat input_format = ImageFormat::UNKNOWN,
                                ImageFormat output_format = ImageFormat::I420) override
    {
        if (input_format == ImageFormat::PNG) {
            return false;
        }

        if (output_format != ImageFormat::I420) {
            return false;
        }

        int width, height, subsamp, colorspace;
        if (tjDecompressHeader3(tj_handle_,
                                encoded.data(),
                                encoded.size(),
                                &width, &height,
                                &subsamp,
                                &colorspace) != 0) {
            return false;
        }

        if (!output.is_valid() ||
            output.width() != width ||
            output.height() != height ||
            output.format() != AxVideoFormat::I420) {

            try {
                output = Ax::VideoBuffer(width, height, AxVideoFormat::I420);
            } catch (const std::exception&) {
                return false;
            }
        }

        int result = tjDecompressToYUV2(
            tj_handle_,
            encoded.data(),
            encoded.size(),
            output.data(),
            width,
            1,
            height,
            TJFLAG_FASTDCT
        );

        return result == 0;
    }
};

#endif
