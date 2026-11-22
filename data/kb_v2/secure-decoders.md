# Secure decoders and protected output

## Secure playback
Protected content at higher levels needs a secure decoder (`FEATURE_SecurePlayback`), usually
named with a `.secure` suffix, rendering to a secure surface.

## Black screenshots
Frames from a secure path are hidden from screenshots and screen recording, which then show black
video. That is expected and not a decoding failure.
