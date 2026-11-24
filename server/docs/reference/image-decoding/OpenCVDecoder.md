# OpenCVDecoder

## Overview
`OpenCVDecoder` is an [ImageDecoder](ImageDecoder.md) backed by `cv::imdecode`. It handles any format OpenCV supports. It is the fallback decoder inside [SIMDDecoder](SIMDDecoder.md).

## Attributes
The class has no public attributes.

## Methods
| Method | Summary | Page |
|---|---|---|
| `OpenCVDecoder()` | Default constructor. | - |
| `decode` | Decode with `cv::imdecode` (`IMREAD_COLOR`). Wraps the input in a thread-local `cv::Mat` header without copying. Ignores the format hint. Returns true if the result is non-empty. | [ImageDecoder.decode](ImageDecoder.decode.md) |
| `decode_ex` | Decode to `BGR`, or to `I420` through `cv::cvtColor(COLOR_BGR2YUV_I420)`. Returns false for other formats. | [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) |
| `decode_to_videobuffer` | Decode, convert to I420 and copy into the buffer. Reallocates the buffer when it is invalid or differs in size or format. Returns false unless `output_format` is `I420`. | [ImageDecoder.decode_to_videobuffer](ImageDecoder.decode_to_videobuffer.md) |
| `name` | Return `"OpenCVDecoder"`. | - |

## Initialization
```cpp
OpenCVDecoder decoder;
```

## Lifecycle
The class holds no per-instance state. `decode` uses a `thread_local` wrapper, so each thread has its own header.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageDecoder](ImageDecoder.md) | Base interface. |
| [SIMDDecoder](SIMDDecoder.md) | Uses it as the fallback. |
| [DecoderFactory](DecoderFactory.md) | Returns it when `HAVE_TURBOJPEG` is not defined. |

## Source Reference
`server/include/decoders/opencv_decoder.hpp::OpenCVDecoder` (lines 9-119)
