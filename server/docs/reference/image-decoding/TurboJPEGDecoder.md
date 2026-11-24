# TurboJPEGDecoder

## Overview
`TurboJPEGDecoder` is a JPEG-only [ImageDecoder](ImageDecoder.md) backed by libjpeg-turbo (TurboJPEG API). It decodes with `TJFLAG_FASTDCT`, and with fast upsampling for BGR. That trades a little accuracy for speed. The class compiles only when `HAVE_TURBOJPEG` is defined. See [Image decoding](../../vision/image-decoding.md).

## Attributes
The class has no public attributes. It owns one TurboJPEG decompressor handle.

## Methods
| Method | Summary | Page |
|---|---|---|
| `TurboJPEGDecoder()` | Create the decompressor handle. Throws `std::runtime_error` if `tjInitDecompress` fails. | - |
| `~TurboJPEGDecoder()` | Destroy the handle. | - |
| `decode` | Decode a JPEG to BGR. Returns false for `PNG`, for a bad header, or for a failed decompression. | [ImageDecoder.decode](ImageDecoder.decode.md) |
| `decode_ex` | Decode to `BGR`, or to `I420` as a single-channel Mat with `height + (height >> 1)` rows. `OpenCVDecoder` uses `height * 3 / 2` rows. Returns false for `PNG` or other formats. | [ImageDecoder.decode_ex](ImageDecoder.decode_ex.md) |
| `decode_to_videobuffer` | The override is private. Reach it only through an `ImageDecoder` reference or pointer. Decode to I420 directly into the buffer, reallocating it on mismatch. Returns false for `PNG`, non-I420 output, or errors. | [ImageDecoder.decode_to_videobuffer](ImageDecoder.decode_to_videobuffer.md) |
| `name` | Return `"TurboJPEGDecoder"`. | - |

## Initialization
```cpp
#ifdef HAVE_TURBOJPEG
TurboJPEGDecoder decoder;   // throws std::runtime_error on failure
#endif
```
The copy constructor and copy assignment are deleted.

## Lifecycle
The constructor creates the handle. The destructor calls `tjDestroy`. The object is non-copyable. Do not use one instance from several threads at once.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageDecoder](ImageDecoder.md) | Base interface. |
| [SIMDDecoder](SIMDDecoder.md) | Owns a `TurboJPEGDecoder` for JPEG input. |
| [OpenCVDecoder](OpenCVDecoder.md) | Handles the formats this class rejects. |

## Source Reference
`server/include/decoders/turbojpeg_decoder.hpp::TurboJPEGDecoder` (lines 18-237)
