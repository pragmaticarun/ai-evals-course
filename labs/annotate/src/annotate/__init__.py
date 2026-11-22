"""annotate: a small, keyboard-driven trace review app (module 9).

    annotate.store   trace JSONL, the review queue, labels per annotator, golden flags
    annotate.render  trace tree and tool-specific views (ffprobe, codec_caps, logcat, search_kb)
    annotate.app     the FastAPI app: review, export, agreement, dashboard
    annotate.cli     `annotate serve ...` and `annotate kappa A.csv B.csv`

Inputs are plain files: spans as JSONL (evalkit.trace), a queue as JSONL, and failure modes as
TOML (evalkit.annotate). Labels are written as evalkit annotation CSVs, one file per annotator.
"""

__version__ = "0.9.0"
