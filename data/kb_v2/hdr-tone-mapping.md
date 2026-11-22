# HDR video looks washed out or too dark

## What the stream signals
HDR10 and HLG streams carry BT.2020 colour and a PQ or HLG transfer function. The decoder output
format reports them in `MediaFormat.KEY_COLOR_TRANSFER` and `KEY_COLOR_STANDARD`.

## When the display path is SDR
If that signal reaches a display path that is not HDR-capable and nothing converts it, colours
look grey and flat or the picture looks very dark. Rendering through `TextureView` composites via
the GPU and often flattens HDR; use `SurfaceView`.

## Tone mapping
On an SDR display, tone-map explicitly, for example with a Media3 Transformer effect, or serve an
SDR rendition.
