# Running out of hardware decoders

## A shared, limited resource
Hardware video decoders are shared by every app on the device and only a few can be active at
once. When the limit is reached, creating or configuring another one fails, often with an
insufficient-resource error.

## Thumbnails and lists
Grids of video thumbnails that each open a decoder exhaust the pool quickly. Decode thumbnails one
at a time, reuse a single decoder, or use `MediaMetadataRetriever`, and release every codec you no
longer need. `CodecCapabilities.getMaxSupportedInstances()` (API 23) gives an upper bound.
