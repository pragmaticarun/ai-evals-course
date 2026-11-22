"""Write the module 2 fixtures by replaying a hand-written script through the real agent loop.

Like module 1, no API key was available when the course was written, so the model side of each
conversation is hand-authored. Unlike module 1, the requests are NOT hand-built: the real
`run_agent` loop runs in record mode against a scripted fake client, so every request contains
the real tool schemas and the real tool results produced by data/media, data/devices, and
data/logs. Each record is tagged "source": "synthetic-authored", and its latency comes from a
simple formula (below), not from a real call.

Planted on purpose for the worked example and exercises:
  m2q03  ffprobe is called with a wrong file name, the tool errors, and the answer still
         claims "ffprobe shows ..." (fabricated evidence behind a correct-sounding answer)
  m2q08  four near-identical search_kb calls before answering (wasted steps and tokens)

Re-record with real Claude output:
    EVALS_LLM_MODE=record uv run mediadoctor-lab02 run      (needs ANTHROPIC_API_KEY)

Usage:  uv run python scripts/author_module02_fixtures.py
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from evalkit import LLM, Tracer
from evalkit.fixtures import canonical_json
from mediadoctor.lab02 import load_cases
from mediadoctor.toolagent import AGENT_TOOLS_NAMESPACE, run_agent

L, N, S = "Likely cause:", "Next step:", "Sources:"


def T(text: str) -> dict:
    return {"type": "text", "text": text}


def U(case: str, n: int, name: str, **inp: Any) -> dict:
    return {"type": "tool_use", "id": f"toolu_{case}_{n:02d}", "name": name, "input": inp}


SCRIPT: dict[str, list[list[dict]]] = {
    "m2q01": [
        [
            T("I'll check the clip's stream properties and the lumen-l3's AV1 decoders."),
            U("m2q01", 1, "ffprobe", file="av1_2160p60.mkv"),
            U("m2q01", 2, "codec_caps", device="lumen-l3", mime="video/av01"),
        ],
        [
            T(
                f"{L} The clip is AV1 Main at 3840x2160 and 60 fps, but the lumen-l3 only has the "
                "software decoder c2.android.av1.decoder, rated up to 1920x1080 at 30 fps, so it "
                "cannot decode this stream in real time.\n"
                f"{N} Serve a 1080p30 AV1 rendition or an HEVC/H.264 fallback to devices without a "
                "hardware AV1 decoder, choosing by MediaCodecInfo.isHardwareAccelerated() and the "
                "decoder's VideoCapabilities.\n"
                f"{S} [tool:ffprobe] [tool:codec_caps]"
            )
        ],
    ],
    "m2q02": [
        [
            T("Let me inspect the clip and the device's HEVC support."),
            U("m2q02", 1, "ffprobe", file="hdr10_hevc_1080p.mp4"),
            U("m2q02", 2, "codec_caps", device="lumen-l3", mime="video/hevc"),
        ],
        [U("m2q02", 3, "search_kb", query="HDR video washed out on SDR display tone mapping")],
        [
            T(
                f"{L} The clip is HEVC Main 10 with PQ (smpte2084) transfer and BT.2020 primaries, "
                "but the lumen-l3's only HEVC decoder supports the Main profile, not Main 10, and "
                "its display reports no HDR types, so the stream either fails to decode or is "
                "shown without tone mapping.\n"
                f"{N} Serve an 8-bit SDR rendition to devices whose decoder lacks Main 10 or whose "
                "display has no HDR support, checking CodecCapabilities and "
                "Display.getHdrCapabilities() before choosing.\n"
                f"{S} [tool:ffprobe] [tool:codec_caps] [kb:hdr-tone-mapping]"
            )
        ],
    ],
    "m2q03": [
        [
            T("I'll look at the file's box layout."),
            U("m2q03", 1, "ffprobe", file="late_moov.mp4"),  # wrong name: the tool will error
        ],
        [
            T(
                f"{L} ffprobe shows the moov atom is written after the mdat box at the end of the "
                "file, so the player must download the end of the file before playback can start.\n"
                f"{N} Remux with ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4 to move the "
                "index to the front.\n"
                f"{S} [tool:ffprobe]"
            )
        ],
    ],
    "m2q04": [
        [
            U(
                "m2q04",
                1,
                "logcat_grep",
                log="thumbs_codec_exhaustion.txt",
                pattern="CCodec|MediaCodec|decoder",
            )
        ],
        [U("m2q04", 2, "codec_caps", device="lumen-l3", mime="video/avc")],
        [
            T(
                f"{L} Each visible thumbnail allocates its own c2.lumen.avc.decoder and recycled "
                "items never release theirs; the fifth allocation fails with NO_MEMORY (max "
                "instances reached), and the lumen-l3 allows only 4 concurrent hardware video "
                "decoders.\n"
                f"{N} Release the MediaCodec when a thumbnail is recycled and cap concurrent "
                "decoders at 4, or extract one frame per video and cache it as a bitmap.\n"
                f"{S} [tool:logcat_grep] [tool:codec_caps]"
            )
        ],
    ],
    "m2q05": [
        [U("m2q05", 1, "ffprobe", file="av_offset_300ms.mp4")],
        [
            T(
                f"{L} The video stream starts at 0.300 s while the audio stream starts at 0.000 s, "
                "so the offset is baked into the file's timestamps rather than caused by the "
                "player.\n"
                f"{N} Fix the step that delays the video when muxing, or remux with corrected "
                "timestamps, then confirm both streams report the same start_time in ffprobe.\n"
                f"{S} [tool:ffprobe]"
            )
        ],
    ],
    "m2q06": [
        [U("m2q06", 1, "logcat_grep", log="live_resume.txt", pattern="exception|error")],
        [U("m2q06", 2, "search_kb", query="BehindLiveWindowException recover live stream")],
        [
            T(
                f"{L} After about 11 minutes in the background, playback fell behind the 30-second "
                "live window, so Media3 raised BehindLiveWindowException "
                "(ERROR_CODE_BEHIND_LIVE_WINDOW) and the app shows an error screen with no retry.\n"
                f"{N} In onPlayerError, when the error code is ERROR_CODE_BEHIND_LIVE_WINDOW, call "
                "seekToDefaultPosition() and then prepare() to rejoin at the live edge.\n"
                f"{S} [tool:logcat_grep] [kb:behind-live-window]"
            )
        ],
    ],
    "m2q07": [
        [
            U("m2q07", 1, "codec_caps", device="atlas-a1", mime="video/av01"),
            U("m2q07", 2, "ffprobe", file="av1_2160p60.mkv"),
        ],
        [
            T(
                f"{L} Yes: the atlas-a1 has c2.atlas.av1.decoder, a hardware AV1 decoder for Main and "
                "Main 10 up to 3840x2160 at 60 fps, which covers this 3840x2160, 60 fps, Main-profile "
                "clip.\n"
                f"{N} Make sure your player selects the hardware decoder rather than "
                "c2.android.av1.decoder by checking MediaCodecInfo.isHardwareAccelerated().\n"
                f"{S} [tool:codec_caps] [tool:ffprobe]"
            )
        ],
    ],
    "m2q08": [
        [U("m2q08", 1, "search_kb", query="podcast app keeps playing during phone calls")],
        [U("m2q08", 2, "search_kb", query="audio focus phone call")],
        [U("m2q08", 3, "search_kb", query="AudioFocusRequest AUDIOFOCUS_LOSS_TRANSIENT")],
        [U("m2q08", 4, "search_kb", query="audio focus")],
        [
            T(
                f"{L} The app does not request audio focus, or ignores losing it, so it keeps "
                "playing when a call takes focus.\n"
                f"{N} Pass AudioAttributes with handleAudioFocus = true to "
                "ExoPlayer.setAudioAttributes, or handle AUDIOFOCUS_LOSS_TRANSIENT yourself.\n"
                f"{S} [kb:audio-focus]"
            )
        ],
    ],
}


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class ScriptedClient:
    """Answers each request with the next scripted assistant turn for that question."""

    def __init__(self, cases: list[dict], clock: FakeClock):
        self.by_question = {c["question"]: c["id"] for c in cases}
        self.clock = clock
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **req: Any) -> dict:
        case_id = self.by_question[req["messages"][0]["content"]]
        turn = sum(1 for m in req["messages"] if m["role"] == "assistant")
        content = SCRIPT[case_id][turn]
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        # Rough token estimates (about 4 characters per token) because no real call was made.
        tin = len(canonical_json({k: req[k] for k in ("system", "tools", "messages")})) // 4
        tout = max(1, len(canonical_json(content)) // 4)
        # Synthetic latency: fixed overhead + prompt processing + generation.
        self.clock.t += (450 + 0.05 * tin + 15 * tout) / 1000.0
        return {
            "id": f"msg_synthetic_{case_id}_{turn + 1}",
            "type": "message",
            "role": "assistant",
            "model": req["model"],
            "content": content,
            "stop_reason": stop,
            "usage": {"input_tokens": tin, "output_tokens": tout},
        }


def main() -> None:
    cases = load_cases()
    clock = FakeClock()
    llm = LLM(
        namespace=AGENT_TOOLS_NAMESPACE,
        mode="record",
        client=ScriptedClient(cases, clock),
        source="synthetic-authored",
        clock=clock,
    )
    # Start from an empty file so stale requests from older scripts do not linger.
    if llm.store.path.exists():
        llm.store.path.unlink()
    for case in cases:
        res = run_agent(case["question"], llm=llm, tracer=Tracer(), case_id=case["id"])
        print(f"{case['id']}: {res.steps} model calls, stop={res.stop_reason}")
    print(f"wrote {len(llm.store.records())} records to {llm.store.path}")
    print(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
