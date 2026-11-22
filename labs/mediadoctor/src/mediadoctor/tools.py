"""MediaDoctor's four tools, their JSON schemas, and a dispatcher.

Every tool is deterministic by default, because tool output becomes part of the next model
request and therefore part of the replay key:

- `search_kb`   keyword search over data/kb/ (traced as a child `retrieval` span)
- `ffprobe`     returns a cached, summarized ffprobe result for a clip in data/media/
                (set MEDIADOCTOR_LIVE_FFPROBE=1 to run the real ffprobe instead)
- `codec_caps`  looks up a (fictional) device profile in data/devices/
- `logcat_grep` regex search over captured logs in data/logs/

Tools raise ToolError for bad input. The agent loop turns that into an `is_error` tool result
and marks the tool span as ERROR, so failed tool calls are visible in the trace.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from evalkit import repo_root
from mediadoctor.kb import load_kb

MAX_LOG_LINES = 20


class ToolError(Exception):
    """Bad tool input. The message is shown to the model, so make it actionable."""


def _data(*parts: str) -> Path:
    return repo_root().joinpath("data", *parts)


def _listing(directory: Path, pattern: str = "*") -> list[str]:
    return sorted(p.name for p in directory.glob(pattern) if p.is_file() and p.name != "README.md")


def _safe_name(name: str, directory: Path, what: str, pattern: str = "*") -> Path:
    available = _listing(directory, pattern)
    if name not in available:  # also rejects paths like ../../etc/passwd
        raise ToolError(f"{what} not found: {name!r}. Available: {', '.join(available)}")
    return directory / name


# --- search_kb ---------------------------------------------------------------------------------


def search_kb(query: str, k: int = 2, tracer: Any = None) -> str:
    k = max(1, min(int(k), 5))
    kb = load_kb()
    if tracer is not None:
        with tracer.span(
            "retrieval",
            {
                "gen_ai.operation.name": "retrieval",
                "gen_ai.retrieval.query.text": query,
                "gen_ai.retrieval.top_k": k,
                "gen_ai.data_source.id": "mediadoctor-kb",
            },
        ) as sp:
            hits = kb.search_scored(query, k)
            sp.set_attribute("mediadoctor.retrieval.doc_ids", [d.id for d, _ in hits])
            sp.set_attribute("mediadoctor.retrieval.scores", [s for _, s in hits])
            tracer.clock.advance(SIMULATED_TOOL_MS["retrieval"])
    else:
        hits = kb.search_scored(query, k)
    results = [{"id": d.id, "title": d.title, "text": d.text} for d, _ in hits]
    return json.dumps({"results": results}, ensure_ascii=False)


# --- ffprobe -----------------------------------------------------------------------------------

_STREAM_KEYS = [
    "index", "codec_type", "codec_name", "profile", "width", "height", "pix_fmt",
    "avg_frame_rate", "color_transfer", "color_primaries", "color_space",
    "start_time", "sample_rate", "channels",
]  # fmt: skip


def mp4_top_level_boxes(path: Path) -> list[str]:
    """Order of top-level ISO-BMFF boxes (ftyp, moov, mdat, ...). Empty for non-MP4 files."""
    if path.suffix.lower() not in {".mp4", ".m4a", ".mov"}:
        return []
    boxes, data = [], path.read_bytes()
    i = 0
    while i + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[i : i + 8])
        if size == 1:  # 64-bit size
            size = struct.unpack(">Q", data[i + 8 : i + 16])[0]
        elif size == 0:  # box runs to end of file
            size = len(data) - i
        boxes.append(kind.decode("latin-1"))
        if size < 8:
            break
        i += size
    return boxes


def summarize_ffprobe(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    fmt = raw.get("format", {})
    streams = []
    for st in raw.get("streams", []):
        keep = {}
        for k in _STREAM_KEYS:
            v = st.get(k)
            if v in (None, "unknown", "N/A", "0/0"):
                continue
            keep[k] = v
        streams.append(keep)
    out: dict[str, Any] = {
        "file": path.name,
        "format": fmt.get("format_name"),
        "duration_s": round(float(fmt.get("duration", 0)), 3),
        "bit_rate": int(fmt.get("bit_rate", 0)),
        "streams": streams,
    }
    boxes = mp4_top_level_boxes(path)
    if boxes:
        out["mp4_top_level_boxes"] = boxes
    return out


def run_real_ffprobe(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe:
        raise ToolError("ffprobe is not installed on this machine")
    proc = subprocess.run(
        [exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, check=False, timeout=30,
    )  # fmt: skip
    if proc.returncode != 0:
        raise ToolError(f"ffprobe failed: {proc.stderr.strip()[:300]}")
    return summarize_ffprobe(json.loads(proc.stdout), path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_cache_path() -> Path:
    return _data("media", "probes.json")


def ffprobe(file: str) -> str:
    path = _safe_name(file, _data("media"), "media file", "*.m*")
    if os.environ.get("MEDIADOCTOR_LIVE_FFPROBE") == "1":
        return json.dumps(run_real_ffprobe(path), sort_keys=True)
    cache = json.loads(probe_cache_path().read_text())
    entry = cache.get(file)
    if entry is None or entry["sha256"] != sha256_file(path):
        raise ToolError(f"probe cache is stale for {file}; run `uv run mediadoctor-lab02 probe`")
    return json.dumps(entry["probe"], sort_keys=True)


def refresh_probe_cache() -> Path:
    cache = {}
    for name in _listing(_data("media"), "*.m*"):
        path = _data("media", name)
        cache[name] = {"sha256": sha256_file(path), "probe": run_real_ffprobe(path)}
    out = probe_cache_path()
    out.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return out


# --- codec_caps --------------------------------------------------------------------------------

_MIME_ALIASES = {
    "av1": "video/av01", "av01": "video/av01", "video/av1": "video/av01",
    "hevc": "video/hevc", "h265": "video/hevc", "h.265": "video/hevc",
    "avc": "video/avc", "h264": "video/avc", "h.264": "video/avc",
}  # fmt: skip


def codec_caps(device: str, mime: str) -> str:
    path = _safe_name(f"{device}.json", _data("devices"), "device profile", "*.json")
    profile = json.loads(path.read_text())
    mime_n = _MIME_ALIASES.get(mime.strip().lower(), mime.strip().lower())
    decoders = [d for d in profile["decoders"] if d["mime"] == mime_n]
    return json.dumps(
        {
            "device": profile["device"],
            "android_api_level": profile["android_api_level"],
            "mime": mime_n,
            "decoders": decoders,
            "display_hdr_types": profile["display"]["hdr_types"],
            "widevine_security_level": profile["widevine_security_level"],
            "max_concurrent_hw_video_decoders": profile["max_concurrent_hw_video_decoders"],
        },
        sort_keys=True,
    )


# --- logcat_grep -------------------------------------------------------------------------------


def logcat_grep(log: str, pattern: str) -> str:
    path = _safe_name(log, _data("logs"), "log file", "*.txt")
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ToolError(f"invalid regex {pattern!r}: {exc}") from exc
    lines = path.read_text().splitlines()
    hits = [f"L{i}: {line}" for i, line in enumerate(lines, 1) if rx.search(line)]
    shown = hits[:MAX_LOG_LINES]
    return json.dumps(
        {"log": log, "pattern": pattern, "matches": len(hits), "lines": shown}, ensure_ascii=False
    )


# --- schemas and dispatch ----------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_kb",
        "description": "Search the MediaDoctor knowledge base of Android and multimedia notes. "
        "Returns the best matching documents with their ids (cite them as [kb:<id>]).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Results (default 2).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ffprobe",
        "description": "Inspect a sample media file from data/media/: container, duration, streams "
        "(codec, profile, size, frame rate, colour transfer, start_time) and, for MP4, the order "
        "of top-level boxes such as moov and mdat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Exact file name, e.g. clip.mp4."}
            },
            "required": ["file"],
        },
    },
    {
        "name": "codec_caps",
        "description": "Look up a device profile's decoders for a MIME type (hardware or software, "
        "profiles, max size and frame rate), plus display HDR support, Widevine level, and the "
        "maximum number of concurrent hardware video decoders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Device id, e.g. lumen-l3."},
                "mime": {
                    "type": "string",
                    "description": "e.g. video/av01, video/hevc, video/avc.",
                },
            },
            "required": ["device", "mime"],
        },
    },
    {
        "name": "logcat_grep",
        "description": "Search a captured logcat file from data/logs/ with a case-insensitive regex. "
        f"Returns at most {MAX_LOG_LINES} matching lines with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "log": {"type": "string", "description": "Exact log file name, e.g. crash.txt."},
                "pattern": {"type": "string", "description": "Python regular expression."},
            },
            "required": ["log", "pattern"],
        },
    },
]

# Simulated durations used only by the virtual clock in replay mode, so replayed traces have
# realistic, stable timings. Live runs measure real time instead.
SIMULATED_TOOL_MS = {
    "search_kb": 4.0,
    "retrieval": 6.0,
    "ffprobe": 45.0,
    "codec_caps": 2.0,
    "logcat_grep": 8.0,
}


def run_tool(name: str, arguments: dict[str, Any], tracer: Any = None) -> str:
    try:
        if name == "search_kb":
            return search_kb(arguments["query"], arguments.get("k", 2), tracer=tracer)
        if name == "ffprobe":
            return ffprobe(arguments["file"])
        if name == "codec_caps":
            return codec_caps(arguments["device"], arguments["mime"])
        if name == "logcat_grep":
            return logcat_grep(arguments["log"], arguments["pattern"])
    except KeyError as exc:
        raise ToolError(f"missing required argument {exc.args[0]!r} for tool {name}") from exc
    raise ToolError(f"unknown tool {name!r}")
