# Low-latency decoding

## The platform feature
On API 30 and later, decoders that support `FEATURE_LowLatency` can be configured with
`KEY_LOW_LATENCY = 1` to output each frame as soon as it is decoded, for game streaming or video
calls.

## Checking support
Check the feature on the chosen decoder before setting the key. Vendor-specific low-latency keys
exist on some chips but are not portable.
