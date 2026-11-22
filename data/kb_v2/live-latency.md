# Live stream latency and catch-up

## Target live offset
`MediaItem.LiveConfiguration` sets how far behind the live edge playback aims to stay
(`targetOffsetMs`), and the minimum and maximum offsets it accepts. Lower offsets mean lower
latency and more rebuffering on poor networks.

## Catching up by changing speed
Media3 nudges playback speed between a minimum and maximum (for example 0.97 to 1.03) to return to
the target offset instead of seeking. Wider limits catch up faster but can be audible.
