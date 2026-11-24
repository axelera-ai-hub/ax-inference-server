# ImageDecoder

## Overview
`ImageDecoder` is the abstract interface that turns encoded image bytes into raw pixels. The implementations are [OpenCVDecoder](OpenCVDecoder.md), [TurboJPEGDecoder](TurboJPEGDecoder.md) and [SIMDDecoder](SIMDDecoder.md). Only `decode` and `name` are mandatory. `decode_ex` and `decode_to_videobuffer` have defaults that report unsupported conversions. See [Image decoding](../../vision/image-decoding.md).

## Attributes
The interface has no attributes.

## Methods
| Method | Summary | Page |
|---|---|---|
| `decode` | Decode to a BGR `cv::Mat`. | [ImageDecoder.decode](ImageDecoder.decode.md) |
| `decode_ex` | Decode to BGR or another requested output format. | [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) |
| `decode_to_videobuffer` | Decode into an `Ax::VideoBuffer`. | [ImageDecoder.decode_to_videobuffer](ImageDecoder.decode_to_videobuffer.md) |
| `name` | Return a short decoder name for log messages. | - |
| `~ImageDecoder` | Virtual default destructor. | - |

## Initialization
Create an instance through [DecoderFactory](DecoderFactory.md)`::create_decoder`, or construct a concrete subclass directly.

## Lifecycle
The destructor is virtual, so deleting through a base pointer is safe. The interface does not state thread safety. The concrete classes document their own limits.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageFormat](ImageFormat.md) | Format hints for input and output. |
| [DecoderFactory](DecoderFactory.md) | Creates the decoder for this build. |
| [OpenCVDecoder](OpenCVDecoder.md) | Implementation backed by `cv::imdecode`. |
| [TurboJPEGDecoder](TurboJPEGDecoder.md) | JPEG-only implementation. |
| [SIMDDecoder](SIMDDecoder.md) | TurboJPEG with OpenCV fallback. |

## Source Reference
`server/include/decoders/image_decoder.hpp::ImageDecoder` (lines 31-100)
