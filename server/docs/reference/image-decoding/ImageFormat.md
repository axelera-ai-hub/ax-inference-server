# ImageFormat

## Overview
`ImageFormat` is an `enum class` that names the encoded input formats and the decoded output formats of the decoder interface. `JPEG`, `PNG` and `UNKNOWN` describe encoded input. `UNKNOWN` requests auto-detection. `BGR` and `I420` describe decoded output. See [Image decoding](../../vision/image-decoding.md) for the concept.

## Attributes
| Value | Role | Description |
|---|---|---|
| `JPEG` | Input | The input is a JPEG stream. |
| `PNG` | Input | The input is a PNG stream. |
| `UNKNOWN` | Input | The decoder detects the format itself. |
| `BGR` | Output | Decoded 8-bit, 3-channel BGR image. |
| `I420` | Output | Planar YUV 4:2:0. A `cv::Mat` holds it as one channel. `OpenCVDecoder` uses `height * 3 / 2` rows. `TurboJPEGDecoder` uses `height + (height >> 1)` rows. |

## Methods
| Method | Summary | Page |
|---|---|---|
| None | The type is an enumeration. | - |

## Initialization
Use a value directly, for example `ImageFormat::I420`. The default input format of every decoder method is `UNKNOWN`. The default output format is `BGR`, or `I420` for `decode_to_videobuffer`.

## Lifecycle
The type has no state. It is passed by value.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageDecoder](ImageDecoder.md) | Takes `ImageFormat` as input and output hints. |
| [FormatDetection](FormatDetection.md) | Returns `JPEG` or `UNKNOWN` from the leading bytes. |

## Source Reference
`server/include/decoders/image_decoder.hpp::ImageFormat` (lines 15-22)
