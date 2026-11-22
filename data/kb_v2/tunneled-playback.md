# Tunneled video playback

## What tunneling does
With `FEATURE_TunneledPlayback`, the decoder and audio output synchronise in the hardware and the
app no longer handles output buffers. It saves power on TVs and set-top boxes.

## Enabling it
In Media3, enable tunneling in `DefaultTrackSelector` parameters; it is used only when the device
reports support for the selected format. Debug sync problems with tunneling both on and off.
