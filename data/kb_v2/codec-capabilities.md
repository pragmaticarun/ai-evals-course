# Querying codec capabilities

## Listing codecs
`MediaCodecList(REGULAR_CODECS).codecInfos` lists encoders and decoders. Filter on the MIME type
and on `isEncoder()`; prefer names reported as hardware accelerated.

## Profiles and levels
`CodecCapabilities.profileLevels` lists supported profile and level pairs, such as HEVC Main10 at
level 5.1. A stream above the supported level may fail to configure or decode too slowly.

## Sizes and frame rates
`VideoCapabilities.areSizeAndRateSupported(width, height, fps)` answers whether a combination is
supported, and `getSupportedPerformancePoints()` (API 29) lists measured performance.
