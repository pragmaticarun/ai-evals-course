"""evalkit.monitor and the kappa helpers in evalkit.annotate (module 9)."""

import math
import random

import pytest

from evalkit.annotate import Annotation, cohen_kappa, kappa_report
from evalkit.monitor import (
    Pick,
    bernoulli_cusum,
    build_queue,
    new_categories,
    p_chart,
    proportions,
    psi,
    random_sample,
    stable_fraction,
    stratified_sample,
    two_proportion_z,
    weighted_rate,
)


def test_stable_fraction_is_deterministic_and_uniform():
    assert stable_fraction("r0001", "x") == stable_fraction("r0001", "x")
    assert stable_fraction("r0001", "x") != stable_fraction("r0001", "y")
    xs = [stable_fraction(f"k{i}") for i in range(5000)]
    assert all(0 <= x < 1 for x in xs)
    assert abs(sum(xs) / len(xs) - 0.5) < 0.02


def test_random_sample_rate_and_consistency():
    keys = [f"k{i}" for i in range(4000)]
    s = random_sample(keys, 0.1)
    assert 340 < len(s) < 460
    assert random_sample(keys, 0.1) == s  # the same keys every time
    assert set(random_sample(keys, 0.05)) <= set(s)  # a lower rate is a subset


def test_stratified_sample_probabilities():
    strata = {f"a{i}": "big" for i in range(100)} | {f"b{i}": "small" for i in range(2)}
    got = stratified_sample(strata, 5)
    assert sum(1 for k in got if k.startswith("a")) == 5
    assert all(got[k] == 0.05 for k in got if k.startswith("a"))
    assert got["b0"] == got["b1"] == 1.0  # small strata are taken whole


def test_build_queue_signals_first_with_probability_one():
    keys = [f"k{i:03d}" for i in range(300)]
    signals = {"k010": ["tool_error"], "k020": ["thumbs_down", "slow"], "k030": ["slow"]}
    q = build_queue(keys, signals, rate=0.1, signal_order=["thumbs_down", "tool_error", "slow"])
    assert [p.key for p in q[:3]] == ["k020", "k010", "k030"]
    assert all(p.prob == 1.0 for p in q[:3]) and all(p.triggered for p in q[:3])
    rest = q[3:]
    assert rest and all(p.reasons == ("random",) and p.prob == pytest.approx(0.1) for p in rest)
    assert isinstance(q[0], Pick)


def test_build_queue_with_strata_combines_probabilities():
    keys = [f"k{i:03d}" for i in range(200)]
    strata = {k: ("rare" if i < 4 else "common") for i, k in enumerate(keys)}
    q = build_queue(keys, {}, strata, rate=0.1, per_stratum=2)
    rare = [p for p in q if strata[p.key] == "rare"]
    assert len(rare) >= 2
    for p in rare:
        assert p.prob == pytest.approx(1 - 0.9 * 0.5)  # 2 of 4 rare keys, plus the random draw


def test_weighted_rate_undoes_signal_oversampling():
    rng = random.Random(1)
    truth = {f"k{i}": rng.random() < 0.2 for i in range(5000)}
    signals = {k: ["flag"] for k, bad in truth.items() if bad and rng.random() < 0.5}
    q = build_queue(list(truth), signals, rate=0.1)
    vals = {p.key: truth[p.key] for p in q}
    naive = sum(vals.values()) / len(vals)
    weighted = weighted_rate(vals, {p.key: p.prob for p in q})
    week = sum(truth.values()) / len(truth)
    assert naive > week + 0.2  # the queue is mostly failures
    assert abs(weighted - week) < 0.03


def test_psi_and_new_categories():
    ref = ["a"] * 50 + ["b"] * 50
    assert psi(ref, ref) == pytest.approx(0.0)
    assert psi(ref, ["a"] * 55 + ["b"] * 45) < 0.1
    assert psi(ref, ["a"] * 90 + ["b"] * 10) > 0.25
    assert psi(ref, ref + ["c"] * 20) > 0.1  # a brand-new category moves the index
    assert new_categories(["x", "y"], ["y", "z", "z", "w"]) == ["w", "z"]
    assert proportions(["a", "a", "b"]) == {"a": 2 / 3, "b": 1 / 3}


def test_p_chart_limits_widen_with_small_n():
    pts = p_chart(0.1, [("big", 400, 40), ("small", 25, 3), ("high", 100, 30), ("empty", 0, 0)])
    big, small, high, empty = pts
    assert big.ucl == pytest.approx(0.1 + 3 * math.sqrt(0.09 / 400))
    assert small.ucl - small.lcl > big.ucl - big.lcl
    assert small.lcl == 0.0  # clipped
    assert (big.status, small.status, high.status, empty.status) == ("ok", "ok", "high", "empty")


def test_bernoulli_cusum_alarms_after_a_shift_not_before():
    rng = random.Random(3)
    stable = [rng.random() < 0.05 for _ in range(400)]
    shifted = [rng.random() < 0.20 for _ in range(200)]
    c = bernoulli_cusum(stable + shifted, 0.05, 0.10, h=4)
    assert c.alarm_at is not None and 400 <= c.alarm_at < 480
    assert len(c.path) == 600 and min(c.path) >= 0
    up, down = c.weights
    assert up == pytest.approx(math.log(2)) and down < 0
    assert bernoulli_cusum(stable, 0.05, 0.10, h=6).alarm_at is None
    with pytest.raises(ValueError):
        bernoulli_cusum(stable, 0.2, 0.1)


def test_two_proportion_z():
    diff, z, p = two_proportion_z(10, 100, 30, 100)
    assert diff == pytest.approx(0.2) and z > 3 and p < 0.001
    assert two_proportion_z(5, 100, 5, 100)[2] == pytest.approx(1.0)
    assert two_proportion_z(0, 10, 0, 10) == (0.0, 0.0, 1.0)


def test_cohen_kappa_known_values():
    # 20 items: both yes 7, both no 9, A-only 2, B-only 2: p_o = 0.8, p_e from the marginals
    a = ["y"] * 7 + ["n"] * 9 + ["y"] * 2 + ["n"] * 2
    b = ["y"] * 7 + ["n"] * 9 + ["n"] * 2 + ["y"] * 2
    po, pa, pb = 16 / 20, 9 / 20, 9 / 20
    pe = pa * pb + (1 - pa) * (1 - pb)
    assert cohen_kappa(a, b) == pytest.approx((po - pe) / (1 - pe))
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    assert math.isnan(cohen_kappa(["y"] * 5, ["y"] * 5))
    assert cohen_kappa(["y", "n"], ["n", "y"]) == pytest.approx(-1.0)
    with pytest.raises(ValueError):
        cohen_kappa(["y"], ["y", "n"])


def test_kappa_report_per_mode_and_disagreements():
    left = [
        Annotation("c1", "fail", modes=["m1"]),
        Annotation("c2", "fail", modes=["m1", "m2"]),
        Annotation("c3", "pass"),
        Annotation("c4", "pass"),
        Annotation("only-left", "fail", modes=["m1"]),
    ]
    right = [
        Annotation("c1", "fail", modes=["m1"]),
        Annotation("c2", "fail", modes=["m1"]),
        Annotation("c3", "fail", modes=["m2"]),
        Annotation("c4", "pass"),
    ]
    rep = kappa_report(left, right, "L", "R")
    assert rep.common == ["c1", "c2", "c3", "c4"]
    assert rep.observed == 0.75 and rep.disagreements == ["c3"]
    assert rep.per_mode["m1"][1:] == (2, 0, 0)
    assert rep.per_mode["m2"][1:] == (0, 1, 1)
    assert rep.per_mode["m1"][0] == pytest.approx(1.0)


def test_weighted_rate_ci_brackets_the_estimate_and_is_seeded():
    from evalkit.monitor import weighted_rate, weighted_rate_ci

    values = {f"k{i}": i % 3 == 0 for i in range(60)}
    probs = {k: (1.0 if v else 0.2) for k, v in values.items()}  # failures over-sampled
    lo, hi = weighted_rate_ci(values, probs)
    assert lo < weighted_rate(values, probs) < hi
    assert (lo, hi) == weighted_rate_ci(values, probs)  # same seed, same interval


def test_queue_estimate_has_an_interval_that_contains_the_truth():
    from mediadoctor import lab09

    est, ci = lab09.queue_bias(), lab09.queue_bias_intervals()
    lo, hi = ci["queue, weighted by 1/p"]
    assert lo < est["queue, weighted by 1/p"] < hi
    assert lo < est["week (truth)"] < hi
    assert round(lo, 3) == 0.010 and round(hi, 3) == 0.096  # quoted in module 9, Step 3
