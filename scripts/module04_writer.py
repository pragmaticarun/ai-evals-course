"""Stand-in for the synth model when authoring the module 4 fixtures (synthetic-authored).

No API key was used to write the course, so this deterministic writer produces what the synth
prompt asks Claude Haiku for: one user message per tuple, in the persona's voice, with the
evidence named (or left vague), pasted log lines, planted false premises, and novice typos.
It is template-based, so its output is more regular than a real model's; module 4 says so.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

VAGUE = {
    "file": [
        "one of our test clips",
        "the clip QA sent",
        "our trailer",
        "a video from the catalogue",
    ],
    "device": [
        "a customer's phone",
        "one of the budget phones",
        "this one device",
        "the test phone",
    ],
}

# Core statements per topic and goal. {clip} {device} are filled with names or vague references.
CORE: dict[str, dict[str, list[str]]] = {
    "av1-playback": {
        "diagnose": [
            "{clip} stutters badly on {device}",
            "the 4K60 AV1 version ({clip}) drops frames constantly on {device}",
            "playback of {clip} is choppy on {device} but smooth elsewhere",
            "our 4K60 AV1 trailer drops frames constantly on {device}",
        ],
        "how-to": [
            "how should we choose an AV1 rendition that {device} can actually decode in real time",
            "what is the right way to detect whether {device} decodes {clip} in hardware",
            "how do we know whether a phone can decode {clip} in hardware before we serve it",
        ],
        "check": [
            "will {device} play {clip} smoothly",
            "can we ship {clip} as the default rendition for {device}",
            "will {device} play our 4K60 AV1 trailer smoothly",
        ],
        "none": [
            "from which Android version is there an AV1 decoder, and how do we tell hardware from software decoding",
            "4K AV1 is choppy on cheaper phones but fine on flagships, is that a decoder thing",
        ],
    },
    "hdr-colour": {
        "diagnose": [
            "{clip} looks washed out on {device}",
            "colours in {clip} are flat and grey on {device}",
            "{clip} shows a black screen or dull colours on {device}",
            "our HDR10 videos look washed out on {device}",
        ],
        "how-to": [
            "how should we handle HDR10 content like {clip} on phones such as {device}",
            "what do we need to check before sending {clip} to {device}",
            "what should we check on a phone before playing {clip} in HDR",
        ],
        "check": [
            "can {device} show {clip} in proper HDR",
            "is {device} able to decode and display {clip}",
            "can {device} show HDR10 video properly",
        ],
        "none": [
            "how do we detect at runtime whether the screen can show HDR",
            "HDR videos look grey in our app on some phones, what should we check",
        ],
    },
    "mp4-startup": {
        "diagnose": [
            "{clip} takes about 10 seconds to start over HTTP but plays fine after that",
            "startup of {clip} is slow on mobile networks, seeking later is fine",
        ],
        "how-to": [
            "how do we make {clip} start faster for progressive download",
            "what should we change so {clip} starts quickly when streamed",
        ],
        "none": [
            "why do some of our MP4s take ages to start when streamed progressively",
            "what makes a progressive MP4 slow to start",
        ],
    },
    "av-sync": {
        "diagnose": [
            "in {clip} the audio is ahead of the picture by about a third of a second",
            "voices come before the lips move in {clip}",
        ],
        "how-to": [
            "how do we fix the lip sync offset in {clip}",
            "how do we tell whether the A/V offset in {clip} is in the file or the player",
        ],
        "none": [
            "audio and video drift apart in some of our files, where does that usually come from",
            "how do we track down a constant A/V offset",
        ],
    },
    "codec-limits": {
        "diagnose_log": [
            "our thumbnail grid crashes while scrolling on {device}",
            "video thumbnails stop loading after the 4th item on {device}",
        ],
        "diagnose_device": [
            "MediaCodec.configure() fails for our 10-bit HEVC stream on {device}",
            "decoder setup throws CodecException for HEVC Main 10 on {device}",
        ],
        "how-to_log": [
            "how many video decoders can we keep alive at once for thumbnails on {device}",
        ],
        "how-to_device": [
            "how should we check HEVC Main 10 support on {device} before configuring the decoder",
        ],
        "check": [
            "can {device} decode our 10-bit HEVC renditions",
            "will {device} handle eight video thumbnails decoding at once",
        ],
        "none": [
            "can MediaCodec run out of decoder instances, and how do we avoid it",
            "what does NO_MEMORY from a codec usually mean on Android",
        ],
    },
    "live-stream": {
        "diagnose": [
            "our live stream shows an error screen after the app comes back from the background",
            "live playback fails after resuming the app",
        ],
        "how-to": [
            "how should we recover a live stream after the app was in the background for a while",
        ],
        "none": [
            "what should an app do when a live stream throws BehindLiveWindowException",
            "how do we rejoin the live edge after a long pause",
        ],
    },
    "audio-focus": {
        "diagnose": [
            "our podcast app keeps playing during phone calls",
            "audio from our app continues over incoming calls",
        ],
        "how-to": [
            "how do we pause playback when a call comes in",
            "how should a Media3 app handle phone calls and navigation prompts",
        ],
        "none": [],
    },
    "drm-resolution": {
        "diagnose": [
            "we only get SD renditions on {device} while flagships get HD",
            "premium HD titles fall back to 480p on {device}",
        ],
        "how-to": ["how do we find out whether {device} will get HD keys from Widevine"],
        "check": [
            "will {device} get HD renditions of our DRM content",
            "can {device} play our HD Widevine titles",
        ],
        "none": [
            "why is our DRM content capped at SD on some phones",
            "how do we tell whether a device will be allowed HD Widevine playback",
        ],
    },
}

EXPERT_DETAIL = {
    "av1-playback": "We're on Media3 with the default renderers and the MediaCodec path.",
    "hdr-colour": "The stream is HEVC Main 10 with PQ transfer; we render with the default player view.",
    "mp4-startup": "It's served as a plain progressive download with range requests.",
    "av-sync": "Same offset on every device, so I doubt it's audio sink latency.",
    "codec-limits": "Each item owns its own MediaCodec instance for frame extraction.",
    "codec-limits/device": "We query MediaCodecList before configure, but only by MIME type.",
    "live-stream": "HLS live with a 30 s window, Media3 ExoPlayer.",
    "audio-focus": "We use Media3 ExoPlayer with a MediaSession.",
    "drm-resolution": "License requests succeed; the HD keys just never arrive.",
}

TYPO_WORDS = {"the": "teh", "because": "becuase", "really": "realy", "video": "vidoe", "about": "abuot",
              "playback": "playbak", "doesn't": "doesnt", "phone": "phnoe", "start": "strat", "after": "afer"}  # fmt: skip


def _rng(spec: dict[str, Any]) -> random.Random:
    key = "|".join(f"{k}={spec[k]}" for k in sorted(spec) if k != "log_lines")
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:12], 16))


def _core(spec: dict[str, Any], rng: random.Random) -> str:
    topic, goal, ev = spec["topic"], spec["goal"], spec["evidence"]
    table = CORE[topic]
    if ev == "none":
        options = table["none"] or table[goal]
        if topic == "audio-focus":
            options = table[goal]
    elif topic == "codec-limits" and goal != "check":
        options = table[f"{goal}_{'log' if ev == 'log' else 'device'}"]
    else:
        options = table[goal]
    have_file, have_dev = bool(spec.get("file")), bool(spec.get("device"))
    fitting = [
        o
        for o in options
        if ("{clip}" not in o or have_file)
        and ("{device}" not in o or have_dev or topic == "codec-limits")
    ]
    # prefer templates that mention every artefact the tuple provides
    full = [
        o for o in fitting if ("{clip}" in o or not have_file) and ("{device}" in o or not have_dev)
    ]
    text = rng.choice(full or fitting or options)
    vague = spec["ambiguity"] == "missing-detail"
    clip = spec.get("file") or "our clip"
    device = spec.get("device") or "some phones"
    if vague:
        clip = rng.choice(VAGUE["file"]) if spec.get("file") else clip
        device = rng.choice(VAGUE["device"]) if spec.get("device") else device
    if "{clip}" in text and not spec.get("file"):
        text = text.replace("{clip}", "our videos")
    if "{device}" in text and not spec.get("device"):
        text = text.replace(
            "{device}", "the lumen-l3" if topic == "codec-limits" and not vague else device
        )
    return text.format(
        clip=clip, device=device if vague or not spec.get("device") else f"the {device}"
    )


def _frame(spec: dict[str, Any], core: str, rng: random.Random) -> str:
    persona, goal = spec["persona"], spec["goal"]
    question = goal in ("how-to", "check") or any(
        w in core.lower() for w in ("how ", "what ", "why ", "is that", "can ", "will ")
    )
    sentence = core[0].upper() + core[1:] + ("?" if question else ".")
    if persona == "qa-tester":
        if goal == "diagnose":
            n = rng.choice([3, 4, 5])
            return (
                f"Bug MD-{rng.randint(300, 999)}: {sentence} Repro {n}/5. Expected normal playback."
            )
        return f"QA question: {sentence}"
    if persona == "support-agent":
        lead = rng.choice(
            ["A customer writes:", "Ticket from a user:", "Customer report -", "User says"]
        )
        return f"{lead} {core}. What do I tell them?"
    if persona == "media-engineer":
        return sentence
    lead = rng.choice(["", "", "In our app, ", "Quick one: ", "Hey, "])
    return lead + (sentence if not lead else sentence[0].lower() + sentence[1:])


def _novice(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    out = []
    for w in words:
        lw = w.lower()
        if lw in TYPO_WORDS and rng.random() < 0.7:
            w = TYPO_WORDS[lw]
        out.append(w)
    text = " ".join(out).lower().replace("?", "")
    text = re.sub(r"\.\s", ", ", text)  # run-on sentences, but keep file names intact
    text = re.sub(r"\.$", "", text)
    if rng.random() < 0.4:
        text += rng.choice([" pls help", " any idea", " ??", " thx"])
    return text


def write_query(spec: dict[str, Any]) -> str:
    rng = _rng(spec)
    core = _core(spec, rng)
    text = _frame(spec, core, rng)
    if spec.get("premise"):
        p = spec["premise"]
        claim = rng.choice(
            [
                f"I know {p}.",
                f"{p[0].upper() + p[1:]}, so it's not that.",
                f"We already confirmed {p}.",
            ]
        )
        text = f"{claim} {text}" if spec["goal"] != "diagnose" else f"{text} {claim}"
    if spec["expertise"] == "expert":
        key = (
            f"{spec['topic']}/device"
            if f"{spec['topic']}/device" in EXPERT_DETAIL and spec["evidence"] == "device"
            else spec["topic"]
        )
        text = f"{text} {EXPERT_DETAIL[key]}"
    elif spec["expertise"] == "novice":
        text = _novice(text, rng)
    if spec.get("log_lines") and spec["ambiguity"] != "missing-detail":
        intro = rng.choice(["Log:", "logcat:", "here's the log", "Relevant lines:"])
        text = f"{text}\n{intro}\n" + "\n".join(spec["log_lines"])
    elif spec.get("log") and spec["ambiguity"] == "missing-detail":
        text += rng.choice(
            [
                " (we have a log but it's huge)",
                " - logs attached somewhere",
                " I can grab logs if needed",
            ]
        )
    return text


NAIVE_RESPONSE = [
    "Why is my video not playing on Android?",
    "How can I fix video playback issues in ExoPlayer?",
    "What are the best practices for handling video playback errors on Android?",
    "Why does my video stutter on some Android devices?",
    "How can I improve video playback performance in my Android app?",
    "What causes video playback to freeze on Android?",
    "How do I debug MediaCodec errors in my Android app?",
    "Why is my video showing a black screen on Android?",
    "How can I ensure smooth video playback across different Android devices?",
    "What are common causes of video buffering issues on Android?",
    "How do I handle different video formats in ExoPlayer?",
    "Why does my video player crash on certain Android versions?",
    "How can I optimize video streaming performance in my Android app?",
    "What steps should I take to debug video playback issues on Android?",
    "Why is the video quality poor on some Android devices?",
    "How do I fix video and audio sync issues in my Android app?",
    "What are the best practices for using ExoPlayer in Android?",
    "Why does my video take a long time to start playing?",
    "How can I debug ExoPlayer errors effectively?",
    "What causes video stuttering in Android media playback?",
    "How do I implement adaptive bitrate streaming on Android?",
    "Why is my video not playing on some Android devices but works on others?",
    "How can I handle network errors during video playback on Android?",
    "What are common MediaCodec issues on Android and how do I fix them?",
    "How do I debug HDR video playback issues on Android?",
    "Why does my video freeze when switching between apps?",
    "How can I improve video startup time in my Android app?",
    "What are the best tools for debugging media playback on Android?",
    "How do I fix video playback issues on low-end Android devices?",
    "Why is my video player showing an error when resuming playback?",
    "How can I ensure my video plays correctly on all Android devices?",
    "What causes video playback to be choppy on Android?",
    "How do I debug video decoding issues on Android?",
    "Why does ExoPlayer throw a playback exception?",
    "How can I handle video playback errors gracefully in my app?",
    "What are the common causes of video lag on Android?",
    "How do I fix video rendering issues in my Android app?",
    "Why does my video look washed out on some Android devices?",
    "How can I debug video streaming issues on Android?",
    "What are the best practices for video playback on Android TV?",
    "How do I troubleshoot ExoPlayer playback failures?",
    "Why is my video not playing in full screen on Android?",
    "How can I reduce video buffering on Android?",
    "What causes MediaCodec to fail on certain Android devices?",
    "How do I handle different screen resolutions for video playback on Android?",
    "Why does my video stutter when playing 4K content on Android?",
    "How can I debug DRM video playback issues on Android?",
    "What are the best practices for handling video codecs on Android?",
    "How do I fix video playback issues after an Android update?",
    "Why does my Android app crash when playing certain video files?",
]
