# Fragmented MP4 for streaming

## Fragments instead of one index
Fragmented MP4 stores a small header and then a series of `moof` and `mdat` pairs, so a player can
start after the first fragment and adaptive streams can switch between renditions.

## CMAF
CMAF uses fragmented MP4 segments that both HLS and DASH can reference, so one set of files serves
both protocols.
