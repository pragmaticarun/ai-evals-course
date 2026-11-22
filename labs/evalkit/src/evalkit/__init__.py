"""evalkit: the small eval toolkit built up over the course.

Module 1 ships:
  - evalkit.llm       record / replay / live wrapper around the Anthropic Messages API
  - evalkit.fixtures  SHA-256 keyed JSONL fixture store
  - evalkit.config    model roles from config/models.toml
  - evalkit.checks    tiny code-based check runner and pass-rate report

Module 2 adds:
  - evalkit.trace     OpenTelemetry-shaped tracer, JSONL export, OTLP/JSON conversion
  - evalkit.viewer    tool-agnostic trace viewer (also the `evalkit view` command)

Modules 3 to 5 add:
  - evalkit.annotate  annotation CSVs, failure-mode ranking, saturation
  - evalkit.synth     dimensions, tuples, coverage, batching, dedup, splits
  - evalkit.judge     LLM judge specs and prompts, TPR/TNR, corrected pass rate with bootstrap CI

Module 6 adds:
  - evalkit.stats     Wilson and bootstrap intervals, judge-error correction, paired comparisons
                      (McNemar, paired bootstrap), Holm adjustment, pass@k and pass^k, sample sizes
  - LLM(..., trial=n) repeated runs of the same request, replayed separately

Module 7 adds:
  - evalkit.retrieval   recall@k, precision@k, hit@k, reciprocal rank (MRR), nDCG@k
  - evalkit.trajectory  tool recall/precision, order, step efficiency, first failure,
                        transition-failure matrices
  - images in requests  fixture keys hash base64 payloads instead of storing them

Module 8 adds:
  - evalkit.gate     regression gates from paired outcomes (McNemar + Holm, minimum effect, warn
                     margin), flips, and cost and time budgets
  - evalkit.golden   golden-dataset manifests (file hashes, split digests, versions), the held-out
                     guard, and held-out rotation
  - evalkit.hygiene  cross-split near-duplicates, n-gram contamination, stale labels
"""

from evalkit.checks import Check, CheckResult, run_checks, summarize
from evalkit.config import ModelRole, Price, load_models, load_prices, repo_root
from evalkit.fixtures import FixtureMissingError, FixtureStore, request_key
from evalkit.llm import LLM, Mode, text_of
from evalkit.trace import Tracer, VirtualClock, WallClock, load_jsonl, to_otlp_json

__all__ = [
    "LLM",
    "Check",
    "CheckResult",
    "FixtureMissingError",
    "FixtureStore",
    "Mode",
    "ModelRole",
    "Price",
    "Tracer",
    "VirtualClock",
    "WallClock",
    "load_jsonl",
    "load_prices",
    "to_otlp_json",
    "load_models",
    "repo_root",
    "request_key",
    "run_checks",
    "summarize",
    "text_of",
]
