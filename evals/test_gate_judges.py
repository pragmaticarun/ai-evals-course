"""Slow tier: replayed LLM judges on the dev split. Run nightly, by hand, or with the run-judges label."""

import pytest

from evalkit.gate import Status, budget_problems, describe
from mediadoctor import lab08

pytestmark = pytest.mark.judges
JUDGES = lab08.gate_config()["tiers"]["judges"]["judges"]


@pytest.fixture(scope="module")
def gate(base, head_judges):
    return lab08.compare(base.run, head_judges, "judges")


def test_every_judge_call_is_recorded(head_judges):
    assert not head_judges.judge_misses, f"re-record: {head_judges.judge_misses[:5]}"


@pytest.mark.parametrize("judge", JUDGES)
def test_no_regression(gate, judge):
    m = next(x for x in gate.metrics if x.metric == judge)
    assert m.status is not Status.FAIL, describe([m])[0]


def test_judge_tier_within_budget(head_judges):
    live = sum(head_judges.usage.values(), lab08.Usage())
    assert not budget_problems(lab08.budget(), head_judges.replay_seconds, live)
