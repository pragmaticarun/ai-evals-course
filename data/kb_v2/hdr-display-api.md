# Asking the display about HDR

## Display capabilities
`Display.getHdrCapabilities()` (API 24) lists the HDR types a display supports, such as HDR10 and
HLG, with its luminance range. An empty list means an SDR display.

## Simpler checks
`Display.isHdr()` and `Configuration.isScreenHdr()` (both API 26) return a single boolean. Check
the display as well as the decoder: a device can decode HDR10 and still show it on an SDR panel.
