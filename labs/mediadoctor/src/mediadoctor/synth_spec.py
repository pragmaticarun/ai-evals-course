"""MediaDoctor-specific pieces of the module 4 synthetic-data workflow.

Maps a dimension tuple to concrete evidence the tools can inspect (real files in data/), the
false belief to plant for `false-premise` tuples, the log lines to paste, and the prompt that asks
the cheap synth model to write one realistic user message.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from evalkit import load_models, repo_root

Tuple = dict[str, str]

SYNTH_NAMESPACE = "mediadoctor-synth"
SYNTH_PROMPT_VERSION = "v1"

KB_FOR_TOPIC = {
    "av1-playback": "av1-decoding",
    "hdr-colour": "hdr-tone-mapping",
    "mp4-startup": "mp4-faststart",
    "av-sync": "av-sync",
    "codec-limits": "mediacodec-errors",
    "live-stream": "behind-live-window",
    "audio-focus": "audio-focus",
    "drm-resolution": "widevine-levels",
}

LOG_FOR_TOPIC = {"codec-limits": "thumbs_codec_exhaustion.txt", "live-stream": "live_resume.txt"}
LOG_PASTE_LINES = {"thumbs_codec_exhaustion.txt": (11, 14), "live_resume.txt": (5, 8)}


def tuple_key(t: Tuple) -> str:
    return "|".join(f"{k}={t[k]}" for k in sorted(t))


def _pick(t: Tuple, options: list[str], salt: str) -> str:
    h = int(hashlib.sha256(f"{salt}:{tuple_key(t)}".encode()).hexdigest()[:8], 16)
    return options[h % len(options)]


def artefacts_for(t: Tuple) -> dict[str, str]:
    """Concrete evidence for a tuple, chosen deterministically from the files in data/."""
    topic, ev = t["topic"], t["evidence"]
    out: dict[str, str] = {}
    want_file = ev in ("media-file", "file+device")
    want_device = ev in ("device", "file+device")
    if want_file:
        out["file"] = {
            "av1-playback": "av1_2160p60.mkv",
            "hdr-colour": "hdr10_hevc_1080p.mp4",
            "av-sync": "av_offset_300ms.mp4",
            "mp4-startup": _pick(
                t,
                [
                    "progressive_late_moov.mp4",
                    "progressive_late_moov.mp4",
                    "progressive_faststart.mp4",
                ],
                "file",
            ),
        }[topic]
    if want_device:
        if topic in ("av1-playback", "hdr-colour"):
            out["device"] = _pick(t, ["lumen-l3", "atlas-a1"], "device")
        else:
            out["device"] = "lumen-l3"
    if ev == "log":
        out["log"] = LOG_FOR_TOPIC[topic]
    return out


def log_paste(log: str) -> list[str]:
    lo, hi = LOG_PASTE_LINES[log]
    lines = (repo_root() / "data" / "logs" / log).read_text().splitlines()
    return lines[lo - 1 : hi]


def premise_for(t: Tuple, art: dict[str, str]) -> str | None:
    """A false belief for `false-premise` tuples: stated as fact, contradicted by the evidence."""
    if t["ambiguity"] != "false-premise":
        return None
    topic, dev, f = t["topic"], art.get("device"), art.get("file", "")
    if topic == "av1-playback":
        if dev == "lumen-l3":
            return "the lumen-l3 has a hardware AV1 decoder"
        if dev == "atlas-a1":
            return "the atlas-a1 only decodes AV1 in software"
        return "Android has shipped an AV1 decoder since Android 8"
    if topic == "hdr-colour":
        if dev == "lumen-l3":
            return "the lumen-l3 supports HDR10"
        if dev == "atlas-a1":
            return "the atlas-a1 display cannot show HDR"
        return "Display.isHdr() works from API 21"
    if topic == "mp4-startup":
        if "faststart" in f:
            return "the moov atom ended up at the end of the file"
        if f:
            return "the moov atom is already at the front of the file"
        return "faststart only matters for DASH, not progressive MP4"
    if topic == "av-sync":
        return (
            "both streams in the file start at zero"
            if f
            else "an MP4 file cannot carry an A/V offset"
        )
    if topic == "codec-limits":
        if t["evidence"] == "device":
            return "the lumen-l3 decodes HEVC Main 10"
        if t["evidence"] == "log":
            return "the lumen-l3 can run 16 hardware decoders at once"
        return "MediaCodec.flush() releases the decoder instance"
    if topic == "live-stream":
        return (
            "this is an audio focus problem"
            if t["evidence"] == "log"
            else "you can catch BehindLiveWindowException around play()"
        )
    if topic == "audio-focus":
        return "AudioFocusRequest works from API 21"
    if topic == "drm-resolution":
        return (
            "the lumen-l3 is a Widevine L1 device"
            if dev
            else "SD playback is only ever a bandwidth issue"
        )
    raise ValueError(topic)


def expected_tools(t: Tuple) -> list[str]:
    return {
        "none": ["search_kb"],
        "media-file": ["ffprobe"],
        "device": ["codec_caps"],
        "file+device": ["codec_caps", "ffprobe"],
        "log": ["logcat_grep"],
    }[t["evidence"]]


SYNTH_SYSTEM = """\
You write test questions for MediaDoctor, an assistant for Android and multimedia engineers.
You get a JSON description of one person and situation. Write the single message that person
would type into a support chat or bug ticket, and output only that message.

- Sound like the persona at the given expertise. Experts are precise and use API names; novices
  are vague, may misspell words, skip capitals and punctuation, and describe symptoms not causes.
- Mention the given file, device, or log names exactly, unless ambiguity is "missing-detail":
  then refer to them vaguely ("our trailer", "a customer's phone") without naming them.
- If log_lines are given and ambiguity is not "missing-detail", paste them verbatim.
- If a premise is given, state it as something the person believes is true. Do not correct it.
- No greetings, no "I'm experiencing", no "Could you please", no lists of questions.
  One to four sentences, plus any pasted log.

Real messages for style (do not copy their content):
{examples}"""


def style_examples() -> list[dict[str, Any]]:
    path = repo_root() / "data" / "synth" / "beta_queries.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_synth_request(t: Tuple, examples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Step two of the two-step method: one tuple in, one natural-language query out."""
    role = load_models()["synth"]
    examples = examples if examples is not None else style_examples()
    ex = sorted(
        examples, key=lambda e: hashlib.sha256(f"{e['id']}:{tuple_key(t)}".encode()).hexdigest()
    )[:3]
    art = artefacts_for(t)
    spec: dict[str, Any] = {**t, **art}
    if "log" in art:
        spec["log_lines"] = log_paste(art["log"])
    premise = premise_for(t, art)
    if premise:
        spec["premise"] = premise
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": SYNTH_SYSTEM.format(examples="\n".join(f"- {e['query']}" for e in ex)),
        "messages": [{"role": "user", "content": json.dumps(spec, sort_keys=True)}],
    }


NAIVE_PROMPT = (
    "Generate 50 diverse, realistic test questions that developers might ask an AI assistant "
    "for debugging Android media playback. Return one question per line, no numbering."
)


def build_naive_request() -> dict[str, Any]:
    role = load_models()["synth"]
    return {
        "model": role.model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": NAIVE_PROMPT}],
    }
