# Progressive MP4 takes long to start (moov atom at the end)

## Why start-up is slow
Recorders often write the MP4 index, the `moov` atom, at the end of the file. A progressive
download player has to fetch the end of the file before playback can begin.

## Checking the atom order
`ffprobe -v trace file.mp4` shows the top-level atoms in order; look for whether `moov` comes
before `mdat`.

## Fixing the file
Remux with the index first: `ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4`.
