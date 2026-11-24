# FormatDetection::detect

## Summary
Identifies the image format from the magic bytes of the encoded data.

## Detailed Description
### Behavior
The function returns `ImageFormat::JPEG` when the first three bytes are `FF D8 FF`. It returns `ImageFormat::UNKNOWN` in every other case. It returns `UNKNOWN` for PNG data and for input shorter than 3 bytes.

### Concurrency
The function reads its argument and keeps no state. Concurrent calls on distinct or shared const input are safe.

### Constraints
The function inspects only the first three bytes. It does not validate the rest of the stream.

## Signature
```cpp
static ImageFormat detect(const std::vector<uint8_t>& encoded);
```

## Parameters
| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `encoded` | `const std::vector<uint8_t>&` | none | Yes | Compressed image bytes. |

## Returns
`ImageFormat`. `JPEG` for a JPEG signature, otherwise `UNKNOWN`.

## Exceptions
| Exception | Trigger | Recovery |
|---|---|---|
| None | The function does not throw. | - |

## Usage Examples
### Basic
```cpp
#include "decoders/format_detection.hpp"

ImageFormat fmt = FormatDetection::detect(bytes);
if (fmt == ImageFormat::UNKNOWN) {
    // Not JPEG: hand the bytes to OpenCVDecoder.
}
```

## Edge Cases
- An empty vector returns `UNKNOWN`.
- A PNG file returns `UNKNOWN`, not `PNG`.
- A buffer starting with `FF D8 FF` returns `JPEG` even if it is truncated.

## Related APIs
| API | Relationship |
|---|---|
| [FormatDetection](FormatDetection.md) | Owning class. |
| [ImageFormat](ImageFormat.md) | Return type. |
| [SIMDDecoder](SIMDDecoder.md) | Calls `detect` when the input format is `UNKNOWN`. |

## Source Reference
`server/include/decoders/format_detection.hpp::FormatDetection::detect` (lines 21-31)
