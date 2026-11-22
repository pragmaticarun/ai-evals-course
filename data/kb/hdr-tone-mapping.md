# HDR video looks washed out or too dark

HDR10 and HLG streams carry a wide colour gamut (BT.2020) and a high-dynamic-range transfer
function (PQ or HLG). When such a stream reaches a display path that is not HDR-capable and
nothing tone-maps it, colours look flat and grey or the picture looks far too dark.

Checks:
- Ask the display what it supports: `Display.getHdrCapabilities()` (or `Display.isHdr()` on API 26+).
- Render to a `SurfaceView`. `TextureView` composites through the GPU and is a common reason
  HDR output gets flattened.
- Confirm the decoder output format reports the expected colour transfer
  (`MediaFormat.KEY_COLOR_TRANSFER`) and colour standard.
- If the display is SDR, tone-map explicitly (for example with a Media3 Transformer or
  effect pipeline) or serve an SDR rendition.
