# AV1 decoding support on Android

## The platform software decoder
Android 10 (API 29) added a software AV1 decoder, `c2.android.av1.decoder`. It is available on
every device with that release, but it runs on the CPU.

## Hardware decoding depends on the chip
Whether AV1 is decoded in hardware depends on the SoC, not on the Android version. Many recent
devices still have only the software decoder, which can be too slow for 4K or 60 fps.

## Checking before you choose a rendition
List decoders for `video/av01` with `MediaCodecList`, check `MediaCodecInfo.isHardwareAccelerated()`
(API 29 and later), and confirm the size and frame rate with `VideoCapabilities`. Fall back to
VP9, HEVC, or H.264 when only software decoding is available.
