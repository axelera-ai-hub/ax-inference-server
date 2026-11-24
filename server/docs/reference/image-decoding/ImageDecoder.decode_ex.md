# ImageDecoder::decode_ex

## Summary
Decodes an encoded image into a `cv::Mat` in the requested output format.

## Detailed Description
### Behavior
The default implementation supports only `BGR` output and delegates to `decode`. For any other output format it returns false. Subclasses override it to add `I420`. For `I420` the `cv::Mat` is single-channel. [OpenCVDecoder](OpenCVDecoder.md) and the base documentation use `height * 3 / 2` rows. [TurboJPEGDecoder](TurboJPEGDecoder.md) uses `height + (height >> 1)` rows.

### Concurrency
Concurrency behavior depends on the underlying runtime. See the concrete class for limits.

### Constraints
`output_format` must be a decoded format (`BGR` or `I420`). `I420` works only in classes that override the method.

## Signature
```cpp
virtual bool decode_ex(const std::vector<uint8_t>& encoded,
                       cv::Mat& output,
                       ImageFormat input_format = ImageFormat::UNKNOWN,
                       ImageFormat output_format = ImageFormat::BGR);
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `encoded` | `const std::vector<uint8_t>&` | none | Yes | Compressed image bytes. |
| `output` | `cv::Mat&` | none | Yes | Receives the decoded image. |
| `input_format` | `ImageFormat` | `UNKNOWN` | No | Input format hint. |
| `output_format` | `ImageFormat` | `BGR` | No | Requested output format. |

## Returns
`bool`. True on success. False on decode failure or an unsupported output format.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| None declared | The method reports failure through the return value. | Check the return value. |

## Usage Examples
### Basic
```cpp
cv::Mat yuv;
bool ok = decoder->decode_ex(bytes, yuv, ImageFormat::UNKNOWN, ImageFormat::I420);
```

## Edge Cases
- The base class returns false for `I420`. The decoders from `DecoderFactory` override the method and support it.
- `OpenCVDecoder` converts BGR to I420 with `cv::cvtColor`.
- `TurboJPEGDecoder` decodes JPEG directly to YUV.

## Related APIs
| API | Relationship |
|---|---|
| [ImageDecoder.decode](ImageDecoder.decode.md) | Called for BGR output by the default implementation. |
| [OpenCVDecoder](OpenCVDecoder.md) | Overrides it with BGR and I420 support. |
| [TurboJPEGDecoder](TurboJPEGDecoder.md) | Overrides it with BGR and I420 support. |
| [SIMDDecoder](SIMDDecoder.md) | Routes to TurboJPEG or OpenCV. |

## Source Reference
`server/include/decoders/image_decoder.hpp::ImageDecoder::decode_ex` (lines 65-73)
