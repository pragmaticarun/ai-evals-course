# Encoding AV1 on the device

## Encoder availability
Few devices ship a hardware AV1 encoder. Query `MediaCodecList` for encoders of `video/av01`;
if none is hardware backed, encoding on the device is usually too slow for real-time capture.

## Practical settings
Use constant-quality or variable-bitrate modes where supported, keep the key-frame interval
short for seeking, and fall back to HEVC or H.264 for recording. Encoding support says nothing
about decoding support, which is checked separately.
