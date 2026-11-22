"""evalkit: the small eval toolkit built up over the course.

Module 1 ships:
  - evalkit.llm       record / replay / live wrapper around the Anthropic Messages API
  - evalkit.fixtures  SHA-256 keyed JSONL fixture store
  - evalkit.config    model roles from config/models.toml
  - evalkit.checks    tiny code-based check runner and pass-rate report
"""

from evalkit.checks import Check, CheckResult, run_checks, summarize
from evalkit.config import ModelRole, load_models, repo_root
from evalkit.fixtures import FixtureMissingError, FixtureStore, request_key
from evalkit.llm import LLM, Mode, text_of

__all__ = [
    "LLM",
    "Check",
    "CheckResult",
    "FixtureMissingError",
    "FixtureStore",
    "Mode",
    "ModelRole",
    "load_models",
    "repo_root",
    "request_key",
    "run_checks",
    "summarize",
    "text_of",
]
