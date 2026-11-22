"""The eval suite as pytest tests (module 8).

    uv run pytest evals -m "not judges"     # fast tier: every pull request and push (seconds)
    uv run pytest evals -m judges           # judge tier: nightly, by hand, or with the run-judges label

Everything replays from fixtures. EVAL_GATE_BASE_REF names the git ref whose evals/baseline.json the
candidate is compared with (the PR's base); without it, this checkout's baseline is used.
"""

from __future__ import annotations

import os
import time

import pytest

from mediadoctor import lab08


@pytest.fixture(scope="session")
def base():
    return lab08.load_baseline(os.environ.get("EVAL_GATE_BASE_REF") or None)


@pytest.fixture(scope="session")
def head_code():
    return lab08.run_suite(lab08.release_prompt(), ("code",), label="head")


@pytest.fixture(scope="session")
def head_judges():
    start = time.perf_counter()
    run = lab08.run_suite(lab08.release_prompt(), ("judges",), label="head")
    run.replay_seconds = time.perf_counter() - start
    return run
