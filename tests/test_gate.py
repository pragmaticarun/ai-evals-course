import pytest

from evalkit.gate import (
    Budget,
    GateRule,
    Status,
    Usage,
    budget_problems,
    evaluate_gate,
    flips,
    naive_gate,
    paired_outcomes,
)


def outcomes(passes: list[bool]) -> dict[str, bool]:
    return {f"c{i:03d}": p for i, p in enumerate(passes)}


def test_identical_runs_pass():
    a = outcomes([True] * 90 + [False] * 10)
    g = evaluate_gate({"m": (a, dict(a))})
    assert g.status is Status.PASS and not g.blocked
    assert g.metrics[0].result.diff == 0


def test_clear_regression_fails():
    a = outcomes([True] * 100)
    b = outcomes([True] * 85 + [False] * 15)
    g = evaluate_gate({"m": (a, b)})
    assert g.status is Status.FAIL and g.blocked
    assert g.metrics[0].result.a_only == 15


def test_small_sample_cannot_rule_out_a_drop_warns():
    a = outcomes([True, False] * 10)
    b = outcomes([False, True] * 10)  # 10 flips each way: no signal, wide interval
    g = evaluate_gate({"m": (a, b)}, GateRule(margin=0.05))
    assert g.status is Status.WARN


def test_min_effect_ignores_tiny_significant_drops():
    a = outcomes([True] * 2000)
    b = outcomes([True] * 1990 + [False] * 10)
    assert evaluate_gate({"m": (a, b)}, GateRule(min_effect=0.0, draws=200)).blocked
    assert not evaluate_gate({"m": (a, b)}, GateRule(min_effect=0.01, draws=200)).blocked


def test_holm_makes_many_metrics_harder_to_fail():
    a = outcomes([True] * 60)
    b = outcomes([True] * 54 + [False] * 6)  # McNemar p = 0.031 on its own
    alone = evaluate_gate({"m": (a, b)})
    many = evaluate_gate({f"m{i}": (a, b if i == 0 else a) for i in range(4)})
    assert alone.blocked
    assert many.metrics[0].p_adjusted == pytest.approx(4 * alone.metrics[0].p_adjusted)
    assert not many.blocked


def test_none_outcomes_are_left_out():
    ids, a, b, dropped = paired_outcomes({"x": True, "y": None, "z": False}, {"x": True, "y": True})
    assert ids == ["x"] and dropped == 2


def test_flips():
    lost, gained = flips({"a": True, "b": False, "c": True}, {"a": False, "b": True, "c": True})
    assert lost == ["a"] and gained == ["b"]


def test_naive_gate():
    assert naive_gate(0.90, 0.89) is Status.FAIL
    assert naive_gate(0.90, 0.89, tolerance=0.02) is Status.PASS


def test_markdown_table_has_a_row_per_metric():
    a = outcomes([True] * 30)
    md = evaluate_gate({"x": (a, a), "y": (a, a)}).markdown()
    assert md.count("\n") == 3 and "| x |" in md


def test_budget():
    u = Usage(10, 1000, 100, 0.5, 120.0) + Usage(5, 500, 50, 0.25, 60.0)
    assert u.calls == 15 and u.cost_usd == pytest.approx(0.75)
    assert u.live_minutes(concurrency=3) == pytest.approx(1.0)
    assert Usage.from_dict(u.as_dict()) == Usage(15, 1500, 150, 0.75, 180.0)
    b = Budget(replay_seconds=10, live_usd=0.5, live_minutes=0.5, concurrency=1)
    problems = budget_problems(b, 12.0, u)
    assert len(problems) == 3
    assert not budget_problems(Budget(), 1.0, u)
