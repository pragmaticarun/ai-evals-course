"""Write the module 1 fixtures: hand-authored responses stored under real request keys.

WHY THIS EXISTS: the course repo was scaffolded without an Anthropic API key, so the
module 1 fixtures were written by hand in the exact Messages API response shape and stored
under the SHA-256 key of the exact request the lab sends. Every record is tagged
"source": "synthetic-authored". The failures in them are planted on purpose for the
worked example (over-long answers, a missing line, dropped citations, one confident factual
error, one retrieval miss).

To replace them with real Claude output, run locally with a key:

    EVALS_LLM_MODE=record uv run mediadoctor-lab01 compare v1 v2

That overwrites each record with "source": "live". Real output will not reproduce the
planted failures exactly; the lab text tells students to expect that.

Usage:  uv run python scripts/author_synthetic_fixtures.py
"""

from __future__ import annotations

import json

from evalkit import FixtureStore, repo_root
from mediadoctor.agent import AGENT_NAMESPACE, build_request
from mediadoctor.kb import load_kb

L, N, S = "Likely cause:", "Next step:", "Sources:"

V1 = {
    "q01": f"{L} TextureView composites through the GPU in SDR, so the HDR10 (PQ, BT.2020) frames are flattened and look grey.\n{N} Render to a SurfaceView and confirm Display.getHdrCapabilities() lists HDR10 for that screen.\n{S} [kb:hdr-tone-mapping]",
    "q02": f"{L} Older SDR displays cannot show HLG directly, and without tone mapping the picture comes out too dark.\n{N} Check Display.isHdr() on those phones; if it is false, tone-map to SDR or serve an SDR rendition.\n{S} [kb:hdr-tone-mapping]",
    "q03": f"{L} The device most likely has no decoder that supports HEVC Main10 at 4K, so configure() fails.\n{N} Query MediaCodecList and the decoder's CodecCapabilities for the profile, level, and size before configuring, and pick a lower rendition if unsupported.\n{S} [kb:mediacodec-errors]",
    "q04": f"{L} Six simultaneous decoders likely exhaust the device's limited hardware codec instances.\n{N} Release codecs for off-screen items and cap concurrent decoders; log CodecException.diagnosticInfo to confirm.\n{S} [kb:mediacodec-errors]",
    "q05": f"{L} Yes. Android 10 made hardware AV1 decoding a requirement, so any device on Android 10 or newer decodes AV1 in hardware.\n{N} Ship AV1 as the default rendition for Android 10+ devices.\n{S} [kb:av1-decoding]",
    "q06": f"{L} Hardware AV1 support depends on the SoC, so it has to be detected per device.\n{N} Enumerate MediaCodecList for video/av01 and call MediaCodecInfo.isHardwareAccelerated() (API 29+) on each decoder.\n{S} [kb:av1-decoding]",
    "q07": (
        f"{L} While the app was in the background, playback fell behind the live window of the HLS "
        "playlist. Live streams only keep a sliding window of recent segments available on the "
        "server, and once the position the player wants to resume from is older than the oldest "
        "segment still listed, the segments are simply gone. Media3 then reports a "
        "BehindLiveWindowException, which surfaces as a PlaybackException with the error code "
        "ERROR_CODE_BEHIND_LIVE_WINDOW. This is expected behaviour for live content rather than "
        "a bug in your player setup, although a short server-side window or a large target live "
        "offset makes it much more likely, especially on slow networks or after long pauses.\n"
        f"{N} In Player.Listener.onPlayerError, check for ERROR_CODE_BEHIND_LIVE_WINDOW, then call "
        "player.seekToDefaultPosition() and player.prepare() to rejoin at the live edge. You "
        "could also ask the backend team to lengthen the live window.\n"
        f"{S} [kb:behind-live-window]"
    ),
    "q08": f"{L} It means playback fell behind the oldest segment still available in the live window, so the needed media no longer exists.\n{N} Handle it in onPlayerError with seekToDefaultPosition() followed by prepare().\n{S} [kb:behind-live-window]",
    "q09": f"{L} The app is not requesting audio focus or ignores focus loss when a call starts.\n{N} Set AudioAttributes with handleAudioFocus = true on the ExoPlayer, or handle AUDIOFOCUS_LOSS_TRANSIENT yourself.\n{S} [kb:audio-focus]",
    "q10": f"{L} The app does not listen for the becoming-noisy broadcast sent when headphones disconnect.\n{N} Handle ACTION_AUDIO_BECOMING_NOISY and pause playback when it arrives.\n{S} [kb:audio-focus]",
    "q11": f"{L} The provided context covers A/V sync and HDR, not how your playback interacts with navigation prompts, so I cannot tell from it.\n{N} Share how you configure AudioAttributes and audio focus for playback.\n{S} none",
    "q12": f"{L} A constant offset on files from one device usually means the audio and video streams start at different timestamps.\n{N} Compare the streams' start_time values with ffprobe -show_streams; remux with corrected timestamps if they differ by about 300 ms.\n{S} [kb:av-sync]",
    "q13": f"{L} Screen recordings are usually variable frame rate, and drift appears when the pipeline assumes a constant frame rate.\n{N} Check frame timestamps with ffprobe -show_frames and remux or transcode with correct timestamps.\n{S} [kb:av-sync]",
    "q14": f"{L} Counting bytes written to AudioTrack does not tell you when audio is actually played, so video timing drifts.\n{N} Use AudioTrack.getTimestamp() to map audio frames to real time and schedule video against that clock.\n{S} [kb:av-sync]",
    "q15": f"{L} Those devices probably run Widevine L3 (software only), and content owners commonly restrict HD renditions to L1 devices, which is why the license server returns only SD keys there.\n{S} [kb:widevine-levels]",
    "q16": f'{L} You can read the level directly from the DRM framework.\n{N} Call MediaDrm(WIDEVINE_UUID).getPropertyString("securityLevel") and log the result.\n{S} [kb:widevine-levels]',
    "q17": f"{L} Unlocking the bootloader can drop the device from Widevine L1 to L3, and the license server then refuses HD keys.\n{N} Check the reported securityLevel on that phone and log the license response status.\n{S} [kb:widevine-levels]",
    "q18": (
        f"{L} The large file almost certainly has its moov atom, the index that tells the player "
        "where every sample lives, written at the end of the file. Recorders and many encoders "
        "do this by default because they only know the final sample table once recording "
        "stops. A progressive HTTP player cannot start decoding without that index, so it "
        "either downloads most of the 2 GB file or issues extra range requests to fetch the "
        "tail before the first frame appears. Small files hide the problem because fetching "
        "the whole file is quick, which is why only big files are slow to start in your test.\n"
        f"{N} Confirm atom order with ffprobe -v trace, then remux with ffmpeg -i in.mp4 -c copy "
        "-movflags +faststart out.mp4 so the index sits at the front.\n"
        f"{S} [kb:mp4-faststart]"
    ),
    "q19": f"{L} The atom order is visible in ffprobe's trace output.\n{N} Run ffprobe -v trace file.mp4 and see whether type:'moov' appears before or after type:'mdat'.\n{S} [kb:mp4-faststart]",
    "q20": f"{L} Faststart only helps single-file progressive download; adaptive streaming needs segmented media.\n{N} Package fragmented MP4 for DASH or HLS and keep faststart for progressive files.\n{S} [kb:mp4-faststart]",
}

V2 = {
    "q01": f"{L} TextureView flattens HDR10 output to SDR.\n{N} Switch to a SurfaceView.\n{S} [kb:hdr-tone-mapping]",
    "q02": f"{L} The older displays are SDR and HLG is not tone-mapped.\n{N} Check Display.isHdr() and tone-map or serve SDR.\n{S} [kb:hdr-tone-mapping]",
    "q03": f"{L} No decoder on the device supports 4K HEVC Main10.\n{N} Check MediaCodecList capabilities before configuring and fall back to a lower rendition.",
    "q04": f"{L} Too many concurrent hardware decoders.\n{N} Release codecs for off-screen items.\n{S} [kb:mediacodec-errors]",
    "q05": f"{L} Yes, Android 10+ requires hardware AV1 decoding.\n{N} Default to AV1 on Android 10+.\n{S} [kb:av1-decoding]",
    "q06": f"{L} Hardware AV1 depends on the SoC.\n{N} Check isHardwareAccelerated() on video/av01 decoders (API 29+).\n{S} [kb:av1-decoding]",
    "q07": f"{L} Playback fell behind the live window while backgrounded.\n{N} On ERROR_CODE_BEHIND_LIVE_WINDOW, call seekToDefaultPosition() then prepare().\n{S} [kb:behind-live-window]",
    "q08": f"{L} Playback is older than the oldest available live segment.\n{N} Rejoin with seekToDefaultPosition() and prepare().\n{S} [kb:behind-live-window]",
    "q09": f"{L} The app ignores audio focus loss during calls.\n{N} Enable handleAudioFocus in ExoPlayer.setAudioAttributes.",
    "q10": f"{L} No handler for the becoming-noisy broadcast.\n{N} Pause on ACTION_AUDIO_BECOMING_NOISY.\n{S} [kb:audio-focus]",
    "q11": f"{L} The context does not cover this.\n{N} Share your AudioAttributes and focus setup.\n{S} none",
    "q12": f"{L} Audio and video streams start at different timestamps.\n{N} Compare start_time with ffprobe -show_streams.\n{S} [kb:av-sync]",
    "q13": f"{L} Variable frame rate treated as constant.\n{N} Inspect frame timestamps with ffprobe -show_frames.\n{S} [kb:av-sync]",
    "q14": f"{L} Bytes written to AudioTrack are not playback time.\n{N} Schedule video using AudioTrack.getTimestamp().",
    "q15": f"{L} The devices are Widevine L3 and HD is limited to L1.\n{S} [kb:widevine-levels]",
    "q16": f'{L} The level is exposed by MediaDrm.\n{N} Read getPropertyString("securityLevel").\n{S} [kb:widevine-levels]',
    "q17": f"{L} The unlock dropped the device to Widevine L3.\n{N} Check securityLevel and the license response.\n{S} [kb:widevine-levels]",
    "q18": f"{L} The moov atom is at the end of the file.\n{N} Remux with ffmpeg -c copy -movflags +faststart.\n{S} [kb:mp4-faststart]",
    "q19": f"{L} Atom order shows in ffprobe's trace.\n{N} Run ffprobe -v trace and check whether moov precedes mdat.\n{S} [kb:mp4-faststart]",
    "q20": f"{L} Faststart is for progressive download only.\n{N} Use fragmented MP4 for DASH or HLS.\n{S} [kb:mp4-faststart]",
}


def make_response(case_id: str, version: str, model: str, request: dict, text: str) -> dict:
    prompt_chars = len(request["system"]) + len(request["messages"][0]["content"])
    return {
        "id": f"msg_synthetic_{case_id}_{version}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        # Token counts are rough estimates (chars / 4) because no real call was made.
        "usage": {"input_tokens": prompt_chars // 4, "output_tokens": max(1, len(text) // 4)},
    }


def main() -> None:
    root = repo_root()
    kb = load_kb()
    store = FixtureStore(root / "fixtures" / "recorded", AGENT_NAMESPACE)
    with (root / "data" / "datasets" / "module01_queries.jsonl").open() as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    n = 0
    for version, answers in (("v1", V1), ("v2", V2)):
        for case in cases:
            req = build_request(case["query"], version, kb)
            resp = make_response(case["id"], version, req["model"], req, answers[case["id"]])
            store.put(req, resp, source="synthetic-authored")
            n += 1
    print(f"wrote {n} records to {store.path}")


if __name__ == "__main__":
    main()
