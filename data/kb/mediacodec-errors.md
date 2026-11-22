# MediaCodec.CodecException and configure failures

`MediaCodec.CodecException` reports whether an error is transient (`isTransient()`: retry the
same call later) or recoverable (`isRecoverable()`: call `stop()`, `configure()`, `start()`
again). Anything else means releasing the codec and creating a new one.

Common causes:
- The format, profile, or level is not supported by any decoder on the device. Query
  `MediaCodecList` and `MediaCodecInfo.CodecCapabilities` before configuring.
- Too many codec instances are alive at once. Hardware codecs are a shared, limited resource;
  release codecs you no longer use.
- The output `Surface` was released while the codec still used it.

Log the `diagnosticInfo` string from the exception; it names the failing component.
