#!/usr/bin/env bash
# Generate the small sample clips used by MediaDoctor's ffprobe tool (module 2 onward).
# Everything is synthesized with ffmpeg's lavfi test sources, so there are no licensing issues.
# The clips are committed; you only need this script to regenerate them.
# After regenerating, refresh the probe cache:  uv run mediadoctor-lab02 probe
set -euo pipefail
cd "$(dirname "$0")/../data/media"
FF=(ffmpeg -hide_banner -loglevel error -y)
V="testsrc2=size=1280x720:rate=30"
A="sine=frequency=440:sample_rate=48000"

# 1. Progressive MP4 with the moov atom at the END (ffmpeg's default without +faststart)
"${FF[@]}" -f lavfi -i "$V" -f lavfi -i "$A" -t 2 -c:v libx264 -preset veryfast -crf 35 \
  -c:a aac -b:a 64k -map_metadata -1 -fflags +bitexact progressive_late_moov.mp4

# 2. The same content remuxed with the index at the front
"${FF[@]}" -i progressive_late_moov.mp4 -c copy -movflags +faststart -map_metadata -1 \
  -fflags +bitexact progressive_faststart.mp4

# 3. Video starts 300 ms after audio, so audio plays ahead of the picture
"${FF[@]}" -f lavfi -i "$A" -itsoffset 0.3 -f lavfi -i "$V" -t 2 -map 1:v -map 0:a \
  -c:v libx264 -preset veryfast -crf 35 -c:a aac -b:a 64k -map_metadata -1 -fflags +bitexact \
  av_offset_300ms.mp4

# 4. HDR10-style HEVC Main10 with PQ transfer and BT.2020 primaries (signalled, 1 second)
"${FF[@]}" -f lavfi -i "testsrc2=size=1920x1080:rate=24" -t 1 -c:v libx265 -preset ultrafast \
  -x265-params "log-level=error:crf=35:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc" \
  -pix_fmt yuv420p10le -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  -tag:v hvc1 -map_metadata -1 -fflags +bitexact hdr10_hevc_1080p.mp4

# 5. AV1 at 3840x2160, 60 fps (half a second, very low quality to stay small)
"${FF[@]}" -f lavfi -i "testsrc2=size=3840x2160:rate=60" -t 0.5 -c:v libsvtav1 -preset 12 -crf 63 \
  -map_metadata -1 -fflags +bitexact av1_2160p60.mkv

ls -l
