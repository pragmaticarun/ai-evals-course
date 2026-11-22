# Sample clips

Synthesized with ffmpeg test sources by `scripts/make_media.sh` (no third-party content).
`probes.json` caches a summarized ffprobe result per clip, keyed by the clip's SHA-256, so the
`ffprobe` tool is deterministic in replay mode. Refresh it with `uv run mediadoctor-lab02 probe`.
