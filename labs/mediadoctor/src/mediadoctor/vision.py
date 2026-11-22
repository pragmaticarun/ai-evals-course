"""Images as eval inputs (module 7): decoded video frames and audio spectrograms.

Two uses of Claude vision, both replayed from fixtures:

- a vision *judge* per video artifact (blocking, banding): one frame in, PASS (artifact absent) or
  FAIL (artifact present) out, with the same JudgeSpec files and verdict parser as module 5;
- a vision *answer*: MediaDoctor names the defect in a spectrogram, scored by a code check.

The images are small PNGs made by scripts/make_module07_images.sh. Their labels come from how they
were made (data/labels/module07_images.csv). Fixture keys hash the image bytes instead of storing
them (evalkit.fixtures.compact_request), so the fixtures stay small.
"""

from __future__ import annotations

import base64
import csv
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import load_models, repo_root
from evalkit.judge import JudgeSpec

NAMESPACE = "mediadoctor-m7-vision"

VISION_JUDGE_SYSTEM = """\
You inspect one decoded video frame for one kind of compression artifact. Check exactly one
criterion; ignore everything else about the image (content, colours, test patterns).

Criterion: {criterion}

PASS: {pass_def}

FAIL: {fail_def}

Describe what you see that your verdict rests on (where in the frame, what it looks like), then
give the verdict. Respond with JSON only:
{{"critique": "<two or three sentences>", "verdict": "PASS" or "FAIL"}}"""

SPECTROGRAM_SYSTEM = """\
You are MediaDoctor, an assistant for Android and multimedia engineers. The user sends a
spectrogram of an audio clip (time left to right, frequency bottom to top, brighter = louder).

Reply in exactly this format:
Defect: <none, dropout, clipping, or noise>
Evidence: <one sentence on what in the image shows it>"""

SPECTROGRAM_QUESTION = (
    "Here is a spectrogram of a 2-second test tone from our app. Is anything wrong with the audio?"
)

DEFECTS = ("none", "dropout", "clipping", "noise")
DEFECT_RE = re.compile(r"^Defect:\s*(\w+)", re.M | re.I)


@dataclass(frozen=True)
class Image:
    name: str  # file name in data/media/frames/
    kind: str  # frame | spectrogram
    artifact: str  # none, blocking, banding, dropout, clipping
    severity: str  # none, mild, severe
    recipe: str


def frames_dir() -> Path:
    return repo_root() / "data" / "media" / "frames"


def labels_path() -> Path:
    return repo_root() / "data" / "labels" / "module07_images.csv"


@cache
def images() -> dict[str, Image]:
    with labels_path().open(newline="", encoding="utf-8") as fh:
        out = {r["image"]: Image(r["image"], r["kind"], r["artifact"], r["severity"], r["recipe"])
               for r in csv.DictReader(fh)}  # fmt: skip
    missing = [n for n in out if not (frames_dir() / n).is_file()]
    if missing:
        raise FileNotFoundError(f"images listed in {labels_path().name} but missing: {missing}")
    return out


def image_block(name: str) -> dict[str, Any]:
    data = base64.b64encode((frames_dir() / name).read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def judge_request(spec: JudgeSpec, name: str) -> dict[str, Any]:
    role = load_models()["judge"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": VISION_JUDGE_SYSTEM.format(
            criterion=spec.criterion, pass_def=spec.pass_def, fail_def=spec.fail_def
        ),
        "messages": [
            {
                "role": "user",
                "content": [image_block(name), {"type": "text", "text": "Judge this frame."}],
            }
        ],
    }


def spectrogram_request(name: str) -> dict[str, Any]:
    role = load_models()["agent"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": SPECTROGRAM_SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": [image_block(name), {"type": "text", "text": SPECTROGRAM_QUESTION}],
            }
        ],
    }


def defect_of(answer: str) -> str | None:
    m = DEFECT_RE.search(answer)
    return m.group(1).lower() if m and m.group(1).lower() in DEFECTS else None
