"""Fast tier: deterministic code checks on the replayed agent, gated against the base's baseline."""

import pytest

from evalkit.gate import Status, budget_problems, describe
from mediadoctor import lab08

METRICS = [*lab08.gate_config()["tiers"]["code"]["checks"], "all-code-checks"]


@pytest.fixture(scope="module")
def gate(base, head_code):
    return lab08.compare(base.run, head_code, "code")


@pytest.mark.parametrize("metric", METRICS)
def test_no_regression(gate, metric):
    m = next(x for x in gate.metrics if x.metric == metric)
    assert m.status is not Status.FAIL, describe([m])[0]


def test_code_tier_within_budget(head_code):
    live = sum(head_code.usage.values(), lab08.Usage())
    assert not budget_problems(lab08.budget(), head_code.replay_seconds, live)
