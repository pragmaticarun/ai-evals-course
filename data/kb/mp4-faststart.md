# Progressive MP4 takes long to start (moov atom at the end)

An MP4 file's index (the `moov` atom) is often written at the end of the file by recorders and
encoders. A progressive-download player must then fetch the end of the file before playback can
begin, which shows up as a long start delay or extra range requests.

Checks and fix:
- `ffprobe -v trace file.mp4 2>&1 | grep -m2 -E "type:'(moov|mdat)'"` shows which atom comes first.
- Remux with the index at the front: `ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`.
- For adaptive streaming, prefer fragmented MP4 (DASH or HLS) instead.
