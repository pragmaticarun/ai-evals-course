import json
import shutil

import pytest

from evalkit import repo_root
from mediadoctor.tools import (
    TOOLS,
    ToolError,
    codec_caps,
    ffprobe,
    logcat_grep,
    mp4_top_level_boxes,
    probe_cache_path,
    run_real_ffprobe,
    run_tool,
    search_kb,
    sha256_file,
)

MEDIA = repo_root() / "data" / "media"


def test_schemas_cover_the_four_tools():
    assert [t["name"] for t in TOOLS] == ["search_kb", "ffprobe", "codec_caps", "logcat_grep"]
    for t in TOOLS:
        assert t["input_schema"]["type"] == "object" and t["input_schema"]["required"]


def test_search_kb_returns_documents():
    out = json.loads(search_kb("BehindLiveWindowException live stream"))
    assert out["results"][0]["id"] == "behind-live-window"


def test_ffprobe_reads_cache_and_reports_key_facts():
    hdr = json.loads(ffprobe("hdr10_hevc_1080p.mp4"))
    v = hdr["streams"][0]
    assert (v["codec_name"], v["profile"], v["color_transfer"]) == ("hevc", "Main 10", "smpte2084")
    late = json.loads(ffprobe("progressive_late_moov.mp4"))
    assert late["mp4_top_level_boxes"].index("mdat") < late["mp4_top_level_boxes"].index("moov")
    off = json.loads(ffprobe("av_offset_300ms.mp4"))
    starts = {s["codec_type"]: s["start_time"] for s in off["streams"]}
    assert starts == {"video": "0.300000", "audio": "0.000000"}


def test_probe_cache_matches_committed_clips():
    cache = json.loads(probe_cache_path().read_text())
    clips = sorted(p.name for p in MEDIA.iterdir() if p.suffix in {".mp4", ".mkv"})
    assert sorted(cache) == clips
    for name in clips:
        assert cache[name]["sha256"] == sha256_file(MEDIA / name)


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_cache_agrees_with_real_ffprobe_on_stable_fields():
    cache = json.loads(probe_cache_path().read_text())
    for name, entry in cache.items():
        live = run_real_ffprobe(MEDIA / name)
        for a, b in zip(entry["probe"]["streams"], live["streams"], strict=True):
            # Fields that are stable across ffprobe versions; others (profile spelling, bit rates,
            # tags) may differ slightly between FFmpeg releases, e.g. on CI runners.
            for k in ("codec_name", "width", "height", "color_transfer"):
                assert a.get(k) == b.get(k), (name, k)
            if a.get("start_time") and b.get("start_time"):
                assert abs(float(a["start_time"]) - float(b["start_time"])) < 0.05, name


def test_mp4_boxes_differ_between_late_and_faststart():
    assert mp4_top_level_boxes(MEDIA / "progressive_faststart.mp4")[1] == "moov"
    assert mp4_top_level_boxes(MEDIA / "progressive_late_moov.mp4")[-1] == "moov"
    assert mp4_top_level_boxes(MEDIA / "av1_2160p60.mkv") == []


@pytest.mark.parametrize(
    "bad", ["late_moov.mp4", "../../config/models.toml", "/etc/passwd", "probes.json"]
)
def test_ffprobe_rejects_unknown_or_unsafe_names(bad):
    with pytest.raises(ToolError, match="not found"):
        ffprobe(bad)


def test_codec_caps_aliases_and_fields():
    lumen = json.loads(codec_caps("lumen-l3", "AV1"))
    assert lumen["mime"] == "video/av01"
    assert [d["hardware"] for d in lumen["decoders"]] == [False]
    assert lumen["display_hdr_types"] == [] and lumen["max_concurrent_hw_video_decoders"] == 4
    atlas = json.loads(codec_caps("atlas-a1", "video/av01"))
    assert any(d["hardware"] and d["max_fps_at_max_size"] == 60 for d in atlas["decoders"])
    with pytest.raises(ToolError, match="device profile not found"):
        codec_caps("pixel-99", "video/avc")


def test_logcat_grep():
    out = json.loads(logcat_grep("thumbs_codec_exhaustion.txt", "no_memory"))
    assert out["matches"] == 3 and out["lines"][0].startswith("L11: ")
    with pytest.raises(ToolError, match="invalid regex"):
        logcat_grep("live_resume.txt", "([")


def test_run_tool_errors_are_actionable():
    with pytest.raises(ToolError, match="missing required argument 'file'"):
        run_tool("ffprobe", {})
    with pytest.raises(ToolError, match="unknown tool"):
        run_tool("rm", {})
