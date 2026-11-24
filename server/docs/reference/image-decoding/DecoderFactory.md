# DecoderFactory

## Overview
`DecoderFactory` chooses the [ImageDecoder](ImageDecoder.md) implementation for the build. With `HAVE_TURBOJPEG` defined it returns [SIMDDecoder](SIMDDecoder.md). Otherwise it returns [OpenCVDecoder](OpenCVDecoder.md). See [Image decoding](../../vision/image-decoding.md).

## Attributes
The class has no attributes.

## Methods
| Method | Summary | Page |
|---|---|---|
| `create_decoder` | Return a new `std::unique_ptr<ImageDecoder>`: `SIMDDecoder` or `OpenCVDecoder`. | - |
| `get_info` | Return a one-line `std::string` starting with `Image Decoder: `. | - |

## Initialization
Both methods are static. Call `DecoderFactory::create_decoder()` for a new instance on each call. `get_info()` returns `Image Decoder: TurboJPEG SIMD (JPEG) → OpenCV fallback (PNG/other)` with TurboJPEG, or `Image Decoder: OpenCV only (no SIMD acceleration)` without it.

## Lifecycle
The caller owns the returned `unique_ptr`. The factory keeps no state. Each instance is independent, so create one decoder per decode worker.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageDecoder](ImageDecoder.md) | Return type. |
| [SIMDDecoder](SIMDDecoder.md) | Result when `HAVE_TURBOJPEG` is defined. |
| [OpenCVDecoder](OpenCVDecoder.md) | Result otherwise. |

## Source Reference
`server/include/decoders/decoder_factory.hpp::DecoderFactory` (lines 15-48)
