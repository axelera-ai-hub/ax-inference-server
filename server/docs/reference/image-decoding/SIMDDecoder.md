# SIMDDecoder

## Overview
`SIMDDecoder` is an [ImageDecoder](ImageDecoder.md) that prefers [TurboJPEGDecoder](TurboJPEGDecoder.md) for JPEG input. It falls back to [OpenCVDecoder](OpenCVDecoder.md) otherwise. When the caller passes `UNKNOWN`, it detects the format with [FormatDetection](FormatDetection.md). The OpenCV fallback also serves requests when TurboJPEG is not compiled in, fails to initialize, or fails on the JPEG.

## Attributes
The class has no public attributes. It owns a TurboJPEG decoder (null when unavailable) and an OpenCV fallback.

## Methods
| Method | Summary | Page |
|---|---|---|
| `SIMDDecoder()` | Create the TurboJPEG decoder when compiled in, and the OpenCV fallback. A TurboJPEG construction failure leaves only the fallback. | - |
| `decode` | Decode to BGR. JPEG goes to TurboJPEG, the rest and failures go to OpenCV. | [ImageDecoder.decode](ImageDecoder.decode.md) |
| `decode_ex` | Decode to BGR or I420 with the same routing. | [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) |
| `decode_to_videobuffer` | Decode into an `Ax::VideoBuffer` with the same routing. | [ImageDecoder.decode_to_videobuffer](ImageDecoder.decode_to_videobuffer.md) |
| `name` | Return `"SIMDDecoder"`. | - |

## Initialization
```cpp
SIMDDecoder decoder;
```
[DecoderFactory](DecoderFactory.md)`::create_decoder` returns it when `HAVE_TURBOJPEG` is defined.

## Lifecycle
Each instance owns its decoders. Do not share one instance between threads. The server creates one decoder per decode worker.

## Related Classes
| Class | Relationship |
|---|---|
| [TurboJPEGDecoder](TurboJPEGDecoder.md) | JPEG path. |
| [OpenCVDecoder](OpenCVDecoder.md) | Fallback path. |
| [FormatDetection](FormatDetection.md) | Format auto-detection. |
| [DecoderFactory](DecoderFactory.md) | Creates it. |

## Source Reference
`server/include/decoders/simd_decoder.hpp::SIMDDecoder` (lines 21-133)
