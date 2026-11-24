# FormatDetection

## Overview
`FormatDetection` is a stateless helper class. It identifies the encoded image format from the leading bytes. It recognizes JPEG only. Every other input, including PNG, yields `ImageFormat::UNKNOWN`. [SIMDDecoder](SIMDDecoder.md) calls it when the caller passes `UNKNOWN`.

## Attributes
The class has no attributes.

## Methods
| Method | Summary | Page |
|---|---|---|
| `detect` | Return `JPEG` if the data starts with `FF D8 FF`, otherwise `UNKNOWN`. | [FormatDetection.detect](FormatDetection.detect.md) |

## Initialization
Do not instantiate the class. Call the static method `FormatDetection::detect`.

## Lifecycle
The class holds no state, so it has no lifecycle.

## Related Classes
| Class | Relationship |
|---|---|
| [ImageFormat](ImageFormat.md) | The return type. |
| [SIMDDecoder](SIMDDecoder.md) | Uses `detect` to route JPEG input to TurboJPEG. |

## Source Reference
`server/include/decoders/format_detection.hpp::FormatDetection` (lines 9-32)
