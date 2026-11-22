# MediaCodec.CodecException and configure failures

## Transient and recoverable errors
`CodecException.isTransient()` means retry the same call later. `isRecoverable()` means call
`stop()`, `configure()`, and `start()` again. Anything else means releasing the codec and
creating a new one.

## Common causes
The format, profile, or level is not supported by any decoder on the device; too many codec
instances are alive at once; or the output surface was released while still in use.

## Diagnostics
Log `diagnosticInfo` from the exception; it names the failing component, such as
`c2.qti.avc.decoder`.
