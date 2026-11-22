# Blocking artifacts at low bitrate

## What it looks like
At very low bitrates the picture breaks into visible square blocks, most obvious in motion and in
fine detail. Each block was coded with too few bits to hide its edges.

## Reducing it
Raise the bitrate or lower the resolution for the bitrate you have, keep the codec's deblocking
filter enabled, and prefer a more efficient codec such as HEVC or AV1 where it can be decoded.
