"""Scenario library for the module 3 trace set (synthetic-authored).

Each scenario is one kind of support question with: question phrasings, the tool calls a good run
makes, the correct answer, and the material for each planted failure pattern. The authoring
script (author_module03_fixtures.py) combines a scenario with a pattern to produce one trace and
its reference annotation. Everything here was written for this course; devices are fictional.
"""

from __future__ import annotations

from typing import Any

Call = tuple[str, dict[str, Any]]

S: dict[str, dict[str, Any]] = {}


def scenario(sid: str, **kw: Any) -> None:
    S[sid] = kw


FFP_AV1: Call = ("ffprobe", {"file": "av1_2160p60.mkv"})
FFP_HDR: Call = ("ffprobe", {"file": "hdr10_hevc_1080p.mp4"})
FFP_LATE: Call = ("ffprobe", {"file": "progressive_late_moov.mp4"})
FFP_FAST: Call = ("ffprobe", {"file": "progressive_faststart.mp4"})
FFP_OFF: Call = ("ffprobe", {"file": "av_offset_300ms.mp4"})

scenario(
    "av1-lumen",
    qs=[
        "Our 4K60 AV1 trailer (av1_2160p60.mkv) drops frames constantly on the lumen-l3. Why?",
        "av1_2160p60.mkv plays like a slideshow on lumen-l3 test phones. What's the cause?",
        "QA says the AV1 4K clip av1_2160p60.mkv stutters on the lumen-l3 but not on the atlas-a1. Explain?",
        "Is the lumen-l3 able to play av1_2160p60.mkv smoothly? Users report stutter.",
    ],
    turns=[[FFP_AV1, ("codec_caps", {"device": "lumen-l3", "mime": "video/av01"})]],
    pre="I'll check the clip and the lumen-l3's AV1 decoders.",
    cause="The clip is AV1 Main at 3840x2160 and 60 fps, but the lumen-l3 only has the software "
    "decoder c2.android.av1.decoder, rated up to 1920x1080 at 30 fps, so it cannot keep up.",
    next="Serve a 1080p30 AV1 or an HEVC rendition to devices without a hardware AV1 decoder, "
    "selected with MediaCodecInfo.isHardwareAccelerated() (API 29+) and VideoCapabilities.",
    src="[tool:ffprobe] [tool:codec_caps]",
    bad=[("codec_caps", {"device": "Lumen L3", "mime": "video/av01"}, "lumen-l3")],
    ignored=[
        (
            "The lumen-l3 has a hardware AV1 decoder that handles 4K60, so the stutter must come "
            "from the network or the player's buffer settings.",
            "claims lumen-l3 has a HW AV1 decoder for 4K60; codec_caps shows only "
            "c2.android.av1.decoder (software, 1080p30)",
        ),
        (
            "The AV1 decoder on the lumen-l3 supports 3840x2160, so the problem is likely thermal "
            "throttling during playback.",
            "says the decoder supports 3840x2160 — tool result says max 1920x1080 @30, software",
        ),
    ],
    generic=(
        "High-resolution AV1 is demanding and some phones decode it in software, which can stutter.",
        "Check whether the device has a hardware AV1 decoder.",
        "none",
    ),
    vague="Try a different device or lower the quality.",
)

scenario(
    "av1-atlas",
    qs=[
        "Will the atlas-a1 decode av1_2160p60.mkv in hardware?",
        "Can we ship av1_2160p60.mkv as the default rendition for the atlas-a1?",
        "Does the atlas-a1 have enough AV1 decoding power for av1_2160p60.mkv at full frame rate?",
    ],
    turns=[[("codec_caps", {"device": "atlas-a1", "mime": "video/av01"}), FFP_AV1]],
    pre="Checking the atlas-a1's AV1 decoders and the clip's properties.",
    cause="Yes: the atlas-a1 has c2.atlas.av1.decoder, a hardware AV1 decoder for Main and Main10 "
    "up to 3840x2160 at 60 fps, which covers this AV1 Main 3840x2160 60 fps clip.",
    next="Make sure the player picks c2.atlas.av1.decoder rather than the software "
    "c2.android.av1.decoder, checking MediaCodecInfo.isHardwareAccelerated().",
    src="[tool:codec_caps] [tool:ffprobe]",
    bad=[("codec_caps", {"device": "atlas_a1", "mime": "av1"}, "atlas-a1")],
    ignored=[
        (
            "No: the atlas-a1 only decodes AV1 in software, and its software decoder tops out at "
            "20 fps at 4K, so this 60 fps clip will stutter.",
            "says atlas-a1 is software-only for AV1; codec_caps lists c2.atlas.av1.decoder "
            "hardware=true 4K60",
        )
    ],
    generic=(
        "Flagship phones from 2025 usually have hardware AV1 decoding, so it probably works.",
        "Test on the device.",
        "none",
    ),
    vague="Test it on a few devices.",
)

scenario(
    "hdr-lumen",
    qs=[
        "hdr10_hevc_1080p.mp4 shows a black screen or washed-out colours on the lumen-l3. Why?",
        "On the lumen-l3 our HDR sample hdr10_hevc_1080p.mp4 looks grey and flat. What's wrong?",
        "Users with a lumen-l3 say hdr10_hevc_1080p.mp4 won't play or looks dull. Root cause?",
    ],
    turns=[
        [FFP_HDR, ("codec_caps", {"device": "lumen-l3", "mime": "video/hevc"})],
        [("search_kb", {"query": "HDR video washed out on SDR display tone mapping"})],
    ],
    kb=["hdr-tone-mapping"],
    pre="Let me inspect the clip and the device's HEVC support.",
    cause="The clip is HEVC Main 10 with PQ (smpte2084) transfer and BT.2020 primaries, but the "
    "lumen-l3's only HEVC decoder supports Main, not Main 10, and its display reports no HDR "
    "types, so the stream either fails to decode or is shown without tone mapping.",
    next="Serve an 8-bit SDR rendition to devices without a Main 10 decoder or an HDR display, "
    "checking CodecCapabilities and Display.getHdrCapabilities() first.",
    src="[tool:ffprobe] [tool:codec_caps] [kb:hdr-tone-mapping]",
    bad=[("ffprobe", {"file": "hdr10_hevc.mp4"}, "hdr10_hevc_1080p.mp4")],
    ignored=[
        (
            "The lumen-l3 decodes HEVC Main 10 in hardware and supports HDR10, so the washed-out "
            "look comes from rendering into a TextureView.",
            "says lumen-l3 supports Main 10 + HDR10; codec_caps: profiles [Main], hdr_types []",
        ),
        (
            "The device supports this stream; the colours are off because the app does not set "
            "the colour space on the surface.",
            "claims the device supports the stream — tool output says no Main 10 and no HDR display",
        ),
    ],
    generic=(
        "HDR content can look washed out on displays without HDR support.",
        "Check HDR support on the device.",
        "none",
    ),
    vague="Check the device settings.",
)

scenario(
    "hdr-atlas",
    qs=[
        "hdr10_hevc_1080p.mp4 looks washed out in our app on the atlas-a1, but fine in the gallery app.",
        "Our player shows hdr10_hevc_1080p.mp4 with flat colours on the atlas-a1. The system gallery is fine. Why?",
        "On the atlas-a1, HDR (hdr10_hevc_1080p.mp4) looks grey only inside our app. Ideas?",
    ],
    turns=[
        [FFP_HDR, ("codec_caps", {"device": "atlas-a1", "mime": "video/hevc"})],
        [("search_kb", {"query": "HDR video washed out tone mapping TextureView SurfaceView"})],
    ],
    kb=["hdr-tone-mapping"],
    pre="I'll check the stream and the atlas-a1's decoder and display support.",
    cause="The device is not the limit: the atlas-a1 has a hardware HEVC decoder with Main10HDR10 "
    "and an HDR10 display, so the app's rendering path is flattening the HDR output, most "
    "likely a TextureView compositing through the GPU.",
    next="Render the video into a SurfaceView instead of a TextureView and confirm the decoder "
    "output format reports PQ transfer.",
    src="[tool:ffprobe] [tool:codec_caps] [kb:hdr-tone-mapping]",
    generic=(
        "HDR video can look washed out when the device does not support HDR.",
        "Check whether the phone supports HDR10.",
        "none",
    ),
    vague="Look into the rendering code.",
)

scenario(
    "latemoov",
    qs=[
        "progressive_late_moov.mp4 takes about 10 seconds to start over HTTP but plays fine afterwards. Why?",
        "Why does progressive_late_moov.mp4 have a long startup delay when streamed progressively?",
        "Startup for progressive_late_moov.mp4 is slow on mobile networks; seeking later is fine. Cause?",
    ],
    turns=[[FFP_LATE]],
    pre="I'll look at the file's box layout.",
    cause="ffprobe shows the top-level boxes in the order ftyp, free, mdat, moov: the moov index "
    "is at the end, so the player must fetch the end of the file before it can start.",
    next="Remux with ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4 to move moov to the front.",
    src="[tool:ffprobe]",
    bad=[("ffprobe", {"file": "late_moov.mp4"}, "progressive_late_moov.mp4")],
    ignored=[
        (
            "The moov box is already at the front of the file, so the delay must come from the "
            "server's slow first byte.",
            "says moov is at the front; ffprobe boxes are ftyp, free, mdat, moov (moov last)",
        )
    ],
    generic=(
        "Slow starts are usually caused by the network or by a large initial buffer.",
        "Reduce the player's initial buffer duration.",
        "none",
    ),
    vague="Optimise the file for streaming.",
)

scenario(
    "faststart",
    qs=[
        "progressive_faststart.mp4 still starts slowly on our CDN. Is the file the problem?",
        "We already used faststart for progressive_faststart.mp4, but startup is still slow. Is the file wrong?",
        "Can you confirm progressive_faststart.mp4 is laid out for progressive playback? Startup is slow.",
    ],
    turns=[[FFP_FAST]],
    pre="Let me check the box order.",
    cause="The file is fine: ffprobe shows ftyp, moov, free, mdat, so the index is at the front "
    "and the player can start after the first bytes; the delay is elsewhere.",
    next="Check the CDN: confirm it honours HTTP range requests and measure time to first byte "
    "for the first request.",
    src="[tool:ffprobe]",
    bad=[("ffprobe", {"file": "faststart.mp4"}, "progressive_faststart.mp4")],
    ignored=[
        (
            "The moov box is at the end of this file, so the player must download it all first.",
            "says moov is at the end; ffprobe shows ftyp, moov, free, mdat (moov 2nd)",
        )
    ],
    generic=(
        "Slow progressive starts are often caused by the moov atom being at the end of the file.",
        "Remux with -movflags +faststart.",
        "none",
    ),
    vague="Look at the CDN configuration.",
)

scenario(
    "avoffset",
    qs=[
        "In av_offset_300ms.mp4 the audio is ahead of the picture by about a third of a second. Why?",
        "av_offset_300ms.mp4 has a lip-sync problem: voices come before the lips move. Player bug?",
        "Is the A/V sync issue in av_offset_300ms.mp4 caused by our player or by the file?",
        "Our QA flagged av_offset_300ms.mp4 for audio leading video. What's going on?",
    ],
    turns=[[FFP_OFF]],
    pre="Checking the stream start times.",
    cause="The video stream starts at 0.300 s and the audio at 0.000 s, so the offset is in the "
    "file's timestamps, not in the player.",
    next="Fix the step that delays video when muxing, or remux with corrected timestamps, then "
    "check that both streams report the same start_time.",
    src="[tool:ffprobe]",
    bad=[("ffprobe", {"file": "av_offset.mp4"}, "av_offset_300ms.mp4")],
    ignored=[
        (
            "Both streams start at 0.000 s, so the file is fine and the player's audio sink "
            "latency is the cause.",
            "says both streams start at 0; ffprobe shows video start_time 0.300",
        )
    ],
    generic=(
        "A/V sync issues are usually caused by the player's audio latency.",
        "Check the player's audio sink.",
        "none",
    ),
    vague="Investigate the sync logic.",
)

scenario(
    "thumbs",
    qs=[
        "Our thumbnail grid crashes on the lumen-l3 while scrolling. The logcat is thumbs_codec_exhaustion.txt.",
        "Video thumbnails fail to load after the 4th item on the lumen-l3 (log: thumbs_codec_exhaustion.txt).",
        "Why does scrolling our video grid on the lumen-l3 throw CodecException? See thumbs_codec_exhaustion.txt.",
        "lumen-l3: thumbnails go blank and we get codec errors (thumbs_codec_exhaustion.txt). Diagnosis?",
    ],
    turns=[
        [
            (
                "logcat_grep",
                {"log": "thumbs_codec_exhaustion.txt", "pattern": "CCodec|MediaCodec|decoder"},
            )
        ],
        [("codec_caps", {"device": "lumen-l3", "mime": "video/avc"})],
    ],
    cause="Each visible thumbnail allocates its own c2.lumen.avc.decoder and recycled items never "
    "release theirs; the fifth allocation fails with NO_MEMORY (max instances reached), and the "
    "lumen-l3 allows only 4 concurrent hardware video decoders.",
    next="Call MediaCodec.release() when a thumbnail is recycled and cap concurrent decoders at 4, "
    "or extract one frame per video and cache it as a bitmap.",
    src="[tool:logcat_grep] [tool:codec_caps]",
    bad=[
        (
            "logcat_grep",
            {"log": "thumbs.txt", "pattern": "CCodec|decoder"},
            "thumbs_codec_exhaustion.txt",
        )
    ],
    ignored=[
        (
            "The lumen-l3 supports 16 concurrent hardware decoders, so the crash is a memory leak "
            "in the bitmap cache.",
            "says 16 concurrent decoders; codec_caps says max_concurrent_hw_video_decoders=4",
        ),
        (
            "The log shows an out-of-memory error in the app's heap, so the bitmaps are too large.",
            "reads NO_MEMORY as Java heap OOM — log says 'max instances reached' (codec instances)",
        ),
    ],
    api=(
        "Call MediaCodec.flush() when a thumbnail is recycled so the decoder instance is freed.",
        "says flush() frees the decoder instance — it only clears buffers; release() frees it",
    ),
    generic=(
        "Thumbnail grids often run out of memory when bitmaps are not recycled.",
        "Use a smaller bitmap size.",
        "none",
    ),
    vague="Profile the app's memory.",
)

scenario(
    "live",
    qs=[
        "After the app comes back from the background our live stream shows an error screen. The log is live_resume.txt.",
        "Live playback fails after resuming the app (log: live_resume.txt). How do we recover?",
        "Our live channel errors out if the app sat in the background ~10 min. Log in live_resume.txt.",
    ],
    turns=[
        [("logcat_grep", {"log": "live_resume.txt", "pattern": "exception|error"})],
        [("search_kb", {"query": "BehindLiveWindowException recover live stream"})],
    ],
    kb=["behind-live-window"],
    cause="After about 11 minutes in the background, playback fell behind the 30-second live window, "
    "so Media3 raised BehindLiveWindowException (ERROR_CODE_BEHIND_LIVE_WINDOW) and the app shows "
    "an error screen with no retry.",
    next="In onPlayerError, when the error code is ERROR_CODE_BEHIND_LIVE_WINDOW, call "
    "seekToDefaultPosition() and then prepare() to rejoin at the live edge.",
    src="[tool:logcat_grep] [kb:behind-live-window]",
    bad=[("logcat_grep", {"log": "live_resume.log", "pattern": "error"}, "live_resume.txt")],
    api=(
        "Wrap player.play() in a try/catch for BehindLiveWindowException and call prepare() in the "
        "catch block.",
        "suggests try/catch around play(); the exception arrives async via onPlayerError",
    ),
    miss=(
        "player crashes when reopened",
        1,
        "The player is likely losing audio focus when the app is reopened and stops playback.",
        "Request audio focus again in onResume.",
        "[kb:audio-focus]",
    ),
    redundant=[
        "live stream error after resume",
        "live stream resume error",
        "error resuming live stream",
    ],
    generic=(
        "Live streams can fail after a long pause.",
        "Restart the player when the app resumes.",
        "none",
    ),
)

scenario(
    "audiofocus",
    qs=[
        "Our podcast app keeps playing during phone calls. How do we fix it?",
        "Audio from our app continues over incoming calls and navigation prompts. Fix?",
        "How should a Media3 app pause for phone calls? Ours keeps playing.",
    ],
    turns=[[("search_kb", {"query": "app keeps playing during calls audio focus"})]],
    kb=["audio-focus"],
    cause="The app does not request audio focus, or ignores losing it, so it keeps playing when a "
    "call takes focus.",
    next="Pass AudioAttributes with handleAudioFocus = true to ExoPlayer.setAudioAttributes, or "
    "request focus with AudioFocusRequest (API 26+) and pause on AUDIOFOCUS_LOSS_TRANSIENT.",
    src="[kb:audio-focus]",
    api=(
        "Request focus with AudioFocusRequest, available from API 21, and pause on AUDIOFOCUS_LOSS.",
        "says AudioFocusRequest is API 21; KB says API 26+",
    ),
    miss=(
        "sound continues when phone rings",
        2,
        "The audio and video clocks drift apart, so audio keeps running after the call starts.",
        "Use the audio clock as the master clock in the renderer.",
        "[kb:av-sync]",
    ),
    redundant=["audio focus phone call", "audio focus", "phone call audio focus"],
)

scenario(
    "widevine",
    qs=[
        "Our app only gets SD renditions on the lumen-l3, while the atlas-a1 gets HD. Same account. Why?",
        "Why is DRM content capped at SD on the lumen-l3?",
        "Premium HD titles fall back to 480p on the lumen-l3 but not the atlas-a1. What's different?",
    ],
    turns=[
        [("codec_caps", {"device": "lumen-l3", "mime": "video/avc"})],
        [("search_kb", {"query": "Widevine L3 HD playback"})],
    ],
    kb=["widevine-levels"],
    cause="The lumen-l3 reports Widevine security level L3 (software only), and content owners "
    "commonly restrict HD keys to L1 devices such as the atlas-a1.",
    next='Read MediaDrm(WIDEVINE_UUID).getPropertyString("securityLevel") on the device and log '
    "the license response to confirm the HD key was refused by policy.",
    src="[tool:codec_caps] [kb:widevine-levels]",
    ignored=[
        (
            "The lumen-l3 is a Widevine L1 device, so the SD cap must come from the bandwidth estimate.",
            "says lumen-l3 is L1; codec_caps shows widevine_security_level L3",
        )
    ],
    api=(
        'Read MediaDrm(WIDEVINE_UUID).getPropertyString("hdcpLevel") to get the Widevine security level.',
        "uses the hdcpLevel property for security level; that's HDCP — should be securityLevel",
    ),
    miss=(
        "why low resolution on this phone",
        2,
        "Low resolution usually comes from a mismatch in timestamps or frame rate.",
        "Remux the content with correct timestamps.",
        "[kb:av-sync]",
    ),
    generic=(
        "Streaming services pick a lower resolution when bandwidth is low.",
        "Check the network speed on the device.",
        "none",
    ),
)

scenario(
    "main10",
    qs=[
        "MediaCodec.configure() throws for our 10-bit HEVC stream on the lumen-l3. Why?",
        "Configuring the decoder for HEVC Main 10 fails on lumen-l3 with CodecException. What to do?",
        "Our 10-bit HEVC renditions crash decoder setup on the lumen-l3. Explain and suggest a fix.",
    ],
    turns=[
        [("codec_caps", {"device": "lumen-l3", "mime": "video/hevc"})],
        [("search_kb", {"query": "MediaCodec configure fails HEVC Main 10"})],
    ],
    kb=["mediacodec-errors"],
    cause="The lumen-l3's only HEVC decoder (c2.lumen.hevc.decoder) supports the Main profile, "
    "not Main 10, so configure() fails for a 10-bit stream.",
    next="Check CodecCapabilities.profileLevels for HEVCProfileMain10 before configuring, and fall "
    "back to an 8-bit rendition when it is missing.",
    src="[tool:codec_caps] [kb:mediacodec-errors]",
    bad=[("codec_caps", {"device": "lumen_l3", "mime": "hevc"}, "lumen-l3")],
    miss=(
        "decoder init fails on 10-bit video",
        2,
        "10-bit video fails because the display cannot show HDR, so the decoder refuses it.",
        "Check Display.getHdrCapabilities() before playing.",
        "[kb:hdr-tone-mapping]",
    ),
    redundant=[
        "MediaCodec configure fails HEVC Main 10",
        "MediaCodec configure HEVC Main 10",
        "configure MediaCodec HEVC Main 10 fails",
    ],
    vague="Check the codec documentation.",
)

scenario(
    "av1-api",
    qs=[
        "From which Android version is there an AV1 decoder, and how do we check for hardware support?",
        "Minimum Android version for AV1 playback, and how to tell hardware from software decoding?",
        "Can we rely on AV1 on Android? Which version added a decoder and how do we detect hardware?",
    ],
    turns=[[("search_kb", {"query": "AV1 software decoder Android version hardware"})]],
    kb=["av1-decoding"],
    cause="Android 10 (API 29) ships the software decoder c2.android.av1.decoder; hardware AV1 "
    "depends on the SoC, not the Android version.",
    next="Enumerate MediaCodecList for video/av01 and use MediaCodecInfo.isHardwareAccelerated() "
    "(API 29+) to prefer hardware decoders.",
    src="[kb:av1-decoding]",
    api=[
        (
            "Use MediaCodecInfo.isHardwareAccelerated(), available since API 21, to detect hardware AV1.",
            "says isHardwareAccelerated() is API 21; it is API 29",
        ),
        (
            "Android 8 (API 26) added the AV1 software decoder c2.android.av1.decoder.",
            "says AV1 software decoder arrived in Android 8 / API 26; KB says Android 10 / API 29",
        ),
    ],
    redundant=[
        "AV1 decoder Android version",
        "AV1 software decoder Android version",
        "AV1 Android version decoder",
    ],
)

scenario(
    "hdr-display-api",
    qs=[
        "How do we detect at runtime whether the screen can show HDR?",
        "Which API tells us if the device display supports HDR10?",
        "Before offering HDR renditions, how should the app check the display?",
    ],
    turns=[[("search_kb", {"query": "check if display supports HDR"})]],
    kb=["hdr-tone-mapping"],
    cause="The display, not the decoder, decides whether HDR can be shown; Android exposes this "
    "through the Display object.",
    next="Call Display.getHdrCapabilities() and check getSupportedHdrTypes() for HDR10 (or "
    "Display.isHdr() on API 26+).",
    src="[kb:hdr-tone-mapping]",
    api=[
        (
            "Call Display.isHdr(), which is available from API 21, and offer HDR when it returns true.",
            "says Display.isHdr() is API 21; KB says API 26",
        ),
        (
            "Query MediaCodecInfo.isHardwareAccelerated() for the HEVC decoder; if true, the display supports HDR.",
            "answers with a decoder API for a display question (isHardwareAccelerated != HDR display)",
        ),
    ],
    miss=(
        "screen HDR support",
        1,
        "HDR support depends on whether the device has a hardware AV1 decoder.",
        "Check MediaCodecList for a hardware video/av01 decoder.",
        "[kb:av1-decoding]",
    ),
    redundant=[
        "check whether display supports HDR",
        "check display supports HDR",
        "HDR display check",
    ],
)

# --- Pattern plan: how many traces of each scenario get each pattern --------------------------
# good = correct run; recovered = tool error then a successful retry (still a pass).
PLAN: dict[str, dict[str, int]] = {
    "av1-lumen": {"ignored": 2, "fabricated": 1, "cite_uncalled": 1, "good": 3},
    "av1-atlas": {"ignored": 1, "giveup": 1, "skipped": 1, "recovered": 1, "good": 3},
    "hdr-lumen": {"ignored": 2, "fabricated": 1, "good": 4},
    "hdr-atlas": {"cite_uncalled": 1, "skipped": 1, "vague": 1, "good": 4},
    "latemoov": {"ignored": 1, "fabricated": 1, "skipped": 1, "recovered": 1, "good": 3},
    "faststart": {"ignored": 1, "giveup": 1, "vague": 1, "good": 4},
    "avoffset": {"ignored": 1, "fabricated": 1, "cite_uncalled": 1, "format": 1, "recovered": 1, "good": 3},
    "thumbs": {"ignored": 2, "api": 1, "fabricated": 1, "skipped": 1, "good": 3},
    "live": {"api": 1, "miss": 1, "giveup": 1, "redundant": 1, "good": 3},
    "audiofocus": {"api": 1, "miss": 2, "redundant": 1, "good": 3},
    "widevine": {"ignored": 1, "api": 1, "miss": 1, "skipped": 1, "good": 3},
    "main10": {"miss": 2, "redundant": 1, "vague": 1, "recovered": 1, "good": 2},
    "av1-api": {"api": 2, "redundant": 1, "format": 1, "good": 3},
    "hdr-display-api": {"api": 2, "miss": 1, "redundant": 1, "good": 3},
}  # fmt: skip
