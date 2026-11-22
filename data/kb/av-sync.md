# Audio and video drift out of sync

Players normally treat the audio clock as the master and schedule video frames against it.
Drift usually comes from wrong timestamps rather than from rendering speed.

Checks:
- Inspect stream start times and timestamps with `ffprobe -show_streams -show_frames`; a large
  `start_time` difference between audio and video streams shows up as constant offset.
- Variable-frame-rate recordings (common from phone cameras) can drift when a pipeline assumes
  a constant frame rate. Remux or transcode with correct timestamps.
- When writing a custom renderer, use `AudioTrack.getTimestamp()` to map audio frames to
  real time instead of counting written bytes.
