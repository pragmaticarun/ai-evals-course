"""evalkit.stats: checked against hand calculations and textbook values."""

import math
import random

import pytest

from evalkit import judge, stats


def test_wilson_matches_known_values():
    lo, hi = stats.wilson_interval(3, 5)
    assert (round(lo, 3), round(hi, 3)) == (0.231, 0.882)
    assert stats.wilson_interval(0, 10)[0] == 0.0 and stats.wilson_interval(10, 10)[1] == 1.0
    lo, hi = stats.wilson_interval(82, 100)
    assert lo < 0.82 < hi and round(hi - lo, 2) == 0.15
    assert stats.wilson_interval(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        stats.wilson_interval(6, 5)


def test_wilson_coverage_is_close_to_nominal():
    rng = random.Random(1)
    n, p, hits = 40, 0.9, 0
    for _ in range(2000):
        k = sum(rng.random() < p for _ in range(n))
        lo, hi = stats.wilson_interval(k, n)
        hits += lo <= p <= hi
    assert 0.92 <= hits / 2000 <= 0.98


def test_bootstrap_ci_is_seeded_and_brackets_the_mean():
    data = [True] * 30 + [False] * 10
    a = stats.bootstrap_ci(data, stats.pass_rate, draws=500, seed=3)
    assert a == stats.bootstrap_ci(data, stats.pass_rate, draws=500, seed=3)
    point, lo, hi = a
    assert point == 0.75 and lo < 0.75 < hi
    wl, wh = stats.wilson_interval(30, 40)
    assert abs(lo - wl) < 0.06 and abs(hi - wh) < 0.06


def test_correction_inverts_the_observation_model():
    obs = stats.observed_pass_rate(0.70, tpr=0.9, tnr=0.6)
    assert math.isclose(obs, 0.75)
    assert math.isclose(stats.corrected_pass_rate(obs, 0.9, 0.6), 0.70)
    with pytest.raises(ValueError):
        stats.corrected_pass_rate(0.5, 0.5, 0.5)


def test_judge_reexports_stats():
    assert judge.corrected_pass_rate is stats.corrected_pass_rate
    assert judge.bootstrap_corrected is stats.bootstrap_corrected
    assert judge.Estimate is stats.Estimate


def test_mcnemar_exact():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert math.isclose(stats.mcnemar_exact(0, 6), 2 / 64)
    assert stats.mcnemar_exact(19, 26) == stats.mcnemar_exact(26, 19)
    assert 0.3 < stats.mcnemar_exact(19, 26) < 0.4


def test_paired_bootstrap_uses_pairs():
    a = [True, False, True, True, False] * 20
    b = [True, True, True, False, True] * 20
    res = stats.paired_bootstrap_diff(a, b, draws=1000, seed=1)
    assert (res.n, res.a_only, res.b_only) == (100, 20, 40)
    assert math.isclose(res.diff, 0.2) and 0 < res.low < 0.2 < res.high
    same = stats.paired_bootstrap_diff(a, a, draws=200)
    assert same.diff == same.low == same.high == 0 and same.p_value == 1.0
    with pytest.raises(ValueError):
        stats.paired_bootstrap_diff(a, b[:-1])


def test_holm():
    adj = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert stats.holm({"x": 0.5, "y": 0.6}) == pytest.approx({"x": 1.0, "y": 1.0})


def test_pass_at_k_and_pass_hat_k():
    assert stats.pass_at_k(5, 3, 1) == stats.pass_hat_k(5, 3, 1) == 0.6
    assert math.isclose(stats.pass_at_k(5, 3, 2), 0.9)
    assert math.isclose(stats.pass_hat_k(5, 3, 2), 0.3)
    assert stats.pass_hat_k(5, 5, 5) == 1.0 and stats.pass_hat_k(5, 4, 5) == 0.0
    assert stats.pass_at_k(5, 0, 5) == 0.0 and stats.pass_at_k(5, 1, 5) == 1.0
    with pytest.raises(ValueError):
        stats.pass_hat_k(3, 1, 4)


def test_trial_summary():
    s = stats.trial_summary({"a": [True, True], "b": [False, False], "c": [True, False]})
    assert (s.always_pass, s.never_pass, s.flaky) == (1, 1, 1)
    assert s.run_rates == (2 / 3, 1 / 3) and math.isclose(s.mean_rate, 0.5)
    with pytest.raises(ValueError):
        stats.trial_summary({"a": [True], "b": [True, False]})


def test_sample_sizes_match_hand_calculations():
    assert stats.n_for_halfwidth(0.8, 0.05) == 246
    assert stats.n_two_proportions(0.80, 0.85) == 906
    assert stats.n_paired(0.15, 0.05) == 469
    with pytest.raises(ValueError):
        stats.n_paired(0.05, 0.10)


def test_minimum_detectable_difference_inverts_sample_size():
    d = stats.mdd_two_proportions(906, 0.80)
    assert 0.049 < d < 0.051
    d = stats.mdd_paired(469, 0.15)
    assert 0.049 < d < 0.051
    assert math.isnan(stats.mdd_paired(5, 0.1))
