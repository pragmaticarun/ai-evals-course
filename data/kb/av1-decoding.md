# AV1 decoding support on Android

Android ships a software AV1 decoder (`c2.android.av1.decoder`) starting with Android 10
(API 29). Hardware AV1 decoding depends on the device's SoC, not on the Android version: many
devices on recent Android releases still decode AV1 in software only, which can be too slow
for high resolutions or frame rates.

Checks:
- Enumerate `MediaCodecList(MediaCodecList.REGULAR_CODECS)` for the MIME type `video/av01`.
- On API 29+, `MediaCodecInfo.isHardwareAccelerated()` tells you whether a decoder is
  hardware backed.
- Use `CodecCapabilities.getVideoCapabilities()` to check supported sizes and frame rates
  before choosing an AV1 rendition; fall back to VP9 or H.264/HEVC when needed.
