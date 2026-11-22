# Audio and video drift out of sync

## Symptoms and the audio clock
Most players use the audio clock as the master and schedule video frames against it, so a
constant offset or a slow drift usually means wrong timestamps, not slow rendering.

## Checking the file's timestamps
Compare the `start_time` of the audio and video streams with `ffprobe -show_streams`. A video
stream that starts 300 ms after the audio stream plays 300 ms late from the first frame. Fix it
at muxing time or remux with corrected timestamps.

## Variable frame rate and custom renderers
Phone recordings are often variable frame rate; pipelines that assume a constant rate drift over
time. In a custom renderer, map audio frames to wall-clock time with `AudioTrack.getTimestamp()`
instead of counting bytes written.
