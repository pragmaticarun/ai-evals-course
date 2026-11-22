# Banding in gradients

## What it looks like
Smooth gradients such as skies or dark scenes show visible steps or contour lines. Eight-bit video
has 256 levels per channel; heavy compression of low-contrast areas removes the in-between values.

## Reducing it
Use 10-bit encoding where possible, raise the bitrate for dark or flat scenes, and add dithering or
a debanding filter (`gradfun` in FFmpeg) before the final 8-bit conversion.
