# ImageDecoder::decode

## Summary
Decodes an encoded image into an 8-bit BGR `cv::Mat`.

## Detailed Description
### Behavior
The pure virtual method decodes `encoded` and writes the result to `bgr_out`. The `format` argument is a hint. `UNKNOWN` requests auto-detection where the implementation supports it.

### Concurrency
Concurrency behavior depends on the underlying runtime. See the concrete class for limits.

### Constraints
Each implementation defines how it uses the hint. [OpenCVDecoder](OpenCVDecoder.md) ignores it. [TurboJPEGDecoder](TurboJPEGDecoder.md) returns false for `PNG`.

## Signature
```cpp
virtual bool decode(const std::vector<uint8_t>& encoded,
                    cv::Mat& bgr_out,
                    ImageFormat format = ImageFormat::UNKNOWN) = 0;
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `encoded` | `const std::vector<uint8_t>&` | none | Yes | Compressed image bytes. |
| `bgr_out` | `cv::Mat&` | none | Yes | Receives the decoded 8-bit, 3-channel BGR image. |
| `format` | `ImageFormat` | `UNKNOWN` | No | Input format hint. |

## Returns
`bool`. True on success, false if the image could not be decoded.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| None declared | The interface reports failure through the return value. | Check the return value. |

## Usage Examples
### Basic
```cpp
auto decoder = DecoderFactory::create_decoder();
cv::Mat bgr;
if (!decoder->decode(bytes, bgr)) {
    // Decoding failed.
}
```

## Edge Cases
- [TurboJPEGDecoder](TurboJPEGDecoder.md) returns false when the JPEG header is invalid.
- The content of `bgr_out` after a failed call is implementation-defined.

## Related APIs
| API | Relationship |
|---|---|
| [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) | Adds an output format selector. |
| [ImageDecoder.decode_to_videobuffer](ImageDecoder.decode_to_videobuffer.md) | Decodes into an `Ax::VideoBuffer`. |
| [ImageFormat](ImageFormat.md) | Hint type. |

## Source Reference
`server/include/decoders/image_decoder.hpp::ImageDecoder::decode` (lines 46-48)
