#!/usr/bin/env bash
# Generate the small still images used by module 7's multimodal lab: video frames with and without
# compression artifacts, and audio spectrograms with and without defects. Everything is synthesized
# with ffmpeg's lavfi sources, at 320x180 (frames) and 320x160 (spectrograms), so the set stays
# well under 1 MB. The images are committed; you only need this script to regenerate them.
# Labels (artifact and severity per image) are in data/labels/module07_images.csv.
set -euo pipefail
cd "$(dirname "$0")/../data/media/frames"
FF=(ffmpeg -hide_banner -loglevel error -y)
S=320x180
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Smooth diagonal colour gradients, computed per pixel with geq (bit-exact on every run; ffmpeg's
# own `gradients` source is not).
grad() {  # grad <1|2|3> -> a lavfi source
  case "$1" in
    1) e="r='60+150*X/W':g='40+170*Y/H':b='200-120*(X+Y)/(W+H)'" ;;
    2) e="r='220-150*Y/H':g='90+100*X/W':b='70+160*(X+Y)/(W+H)'" ;;
    3) e="r='30+200*(X+Y)/(W+H)':g='150-90*X/W':b='60+120*Y/H'" ;;
  esac
  echo "color=c=black:size=$S:rate=1,format=rgb24,geq=$e"
}

grab() {  # grab <input> <output.png> <filter>
  "${FF[@]}" -i "$1" -frames:v 1 -vf "$3" -compression_level 9 "$2"
}

# Clean frames: four different test sources, encoded losslessly.
"${FF[@]}" -f lavfi -i "testsrc2=size=$S:rate=1" -frames:v 1 clean_testsrc.png
"${FF[@]}" -f lavfi -i "mandelbrot=size=$S:rate=1" -frames:v 1 clean_mandelbrot.png
"${FF[@]}" -f lavfi -i "$(grad 1)" -frames:v 1 clean_gradient.png
"${FF[@]}" -f lavfi -i "smptehdbars=size=$S:rate=1" -frames:v 1 clean_bars.png

# Blocking: H.264 at a fixed, very high quantizer with the deblocking filter off.
blocky() {  # blocky <source> <qp> <output>
  "${FF[@]}" -f lavfi -i "$1" -frames:v 1 -c:v libx264 -qp "$2" -x264-params no-deblock=1 \
    -pix_fmt yuv420p "$TMP/b.mp4"
  grab "$TMP/b.mp4" "$3" "format=rgb24"
}
blocky "testsrc2=size=$S:rate=1" 51 blocking_severe_testsrc.png
blocky "mandelbrot=size=$S:rate=1" 51 blocking_severe_mandelbrot.png
blocky "$(grad 2)" 51 blocking_severe_gradient.png
blocky "testsrc2=size=$S:rate=1" 40 blocking_mild_testsrc.png
blocky "mandelbrot=size=$S:rate=1" 40 blocking_mild_mandelbrot.png
blocky "$(grad 2)" 40 blocking_mild_gradient.png

# Banding: smooth gradients with the low bits of each channel removed (posterized).
band() {  # band <gradient> <mask> <output>
  "${FF[@]}" -f lavfi -i "$(grad "$1")" -frames:v 1 \
    -vf "lutrgb=r=bitand(val\,$2):g=bitand(val\,$2):b=bitand(val\,$2)" "$3"
}
band 1 224 banding_severe_a.png
band 2 224 banding_severe_b.png
band 3 224 banding_severe_c.png
band 1 248 banding_mild_a.png
band 2 248 banding_mild_b.png
band 3 248 banding_mild_c.png

# Spectrograms (2 s of audio, 320x160): clean tones, dropouts, and clipping (gain past full scale, then conversion
# to 16-bit integer samples, which clips everything above full scale).
spec() {  # spec <audio filter graph> <output>
  "${FF[@]}" -f lavfi -i "$1" -lavfi "showspectrumpic=s=320x160:legend=0:scale=log" "$2"
}
spec "sine=f=440:d=2,aformat=channel_layouts=mono" spec_clean_440.png
spec "sine=f=1000:d=2,aformat=channel_layouts=mono" spec_clean_1000.png
spec "sine=f=440:d=2,aformat=channel_layouts=mono,volume=enable='between(t,0.8,1.1)':volume=0" spec_dropout_440.png
spec "sine=f=1000:d=2,aformat=channel_layouts=mono,volume=enable='between(t,1.2,1.3)':volume=0" spec_dropout_1000.png
spec "sine=f=440:d=2,aformat=channel_layouts=mono,volume=40,aformat=sample_fmts=s16" spec_clipping_440.png
spec "sine=f=1000:d=2,aformat=channel_layouts=mono,volume=10,aformat=sample_fmts=s16" spec_clipping_1000.png

ls -l
