# Adaptive bitrate and track selection

## How renditions are chosen
Media3's `DefaultTrackSelector` picks a video rendition from the bandwidth estimate and the
constraints you set, such as maximum size or bitrate.

## When quality stays low
A low or slow-to-update bandwidth estimate keeps playback on a low rendition. Check the estimate
from `DefaultBandwidthMeter`, the selector's constraints, and whether the higher renditions are
decodable on the device at all.
