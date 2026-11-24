# ImageDecoder::decode_to_videobuffer

## Summary
Decodes an encoded image directly into an `Ax::VideoBuffer`.

## Detailed Description
### Behavior
The default implementation does nothing and returns false. The concrete decoders override it. They reallocate `output` when it is invalid or its width, height or format differs from the image. They support `I420` output only.

### Concurrency
Concurrency behavior depends on the underlying runtime. See the concrete class for limits.

### Constraints
`output_format` must be `I420`. The default is `I420`.

## Signature
```cpp
virtual bool decode_to_videobuffer(const std::vector<uint8_t>& encoded,
                                   Ax::VideoBuffer& output,
                                   ImageFormat input_format = ImageFormat::UNKNOWN,
                                   ImageFormat output_format = ImageFormat::I420);
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `encoded` | `const std::vector<uint8_t>&` | none | Yes | Compressed image bytes. |
| `output` | `Ax::VideoBuffer&` | none | Yes | Destination buffer. |
| `input_format` | `ImageFormat` | `UNKNOWN` | No | Input format hint. |
| `output_format` | `ImageFormat` | `I420` | No | Requested output format. |

## Returns
`bool`. True on success. False if unsupported, if decoding failed, or if allocation failed.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| None documented | Buffer allocation failures return false. Other exceptions are not documented. | Check the return value. |

## Usage Examples
### Basic
```cpp
Ax::VideoBuffer buffer;
if (!decoder->decode_to_videobuffer(bytes, buffer)) {
    // Decoding or allocation failed.
}
```

## Edge Cases
- A decoder that does not override the method returns false.
- [OpenCVDecoder](OpenCVDecoder.md) assumes `output.size()` equals the packed I420 size of the decoded image.
- [TurboJPEGDecoder](TurboJPEGDecoder.md) returns false for `PNG` input.

## Related APIs
| API | Relationship |
|---|---|
| [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) | Decodes into a `cv::Mat`. |
| [OpenCVDecoder](OpenCVDecoder.md) | Override that converts from BGR. |
| [TurboJPEGDecoder](TurboJPEGDecoder.md) | Override that decodes JPEG directly to I420. |
| [SIMDDecoder](SIMDDecoder.md) | Routes to TurboJPEG or OpenCV. |

## Source Reference
`server/include/decoders/image_decoder.hpp::ImageDecoder::decode_to_videobuffer` (lines 90-96)
