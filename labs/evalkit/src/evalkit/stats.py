"""Statistics for eval metrics (module 6): is a number real, or noise?

Everything here is plain Python (no numpy or scipy), seeded, and small enough to read.

    Intervals       wilson_interval, bootstrap_ci
    Judge error     corrected_pass_rate, bootstrap_corrected   (module 5; evalkit.judge re-exports)
    Comparisons     paired_bootstrap_diff, mcnemar_exact, holm
    Repeated runs   pass_at_k, pass_hat_k, trial_summary
    Sample sizes    n_for_halfwidth, n_two_proportions, n_paired, mdd_two_proportions, mdd_paired

Conventions: outcomes are booleans (True = PASS); rates are fractions in [0, 1]; `level` is the
confidence level (0.95 by default); `alpha` is a two-sided significance level; `power` is 1 - beta.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist, mean, pstdev

# --- Intervals ---------------------------------------------------------------------------------------


def z_value(level: float = 0.95) -> float:
    """Two-sided normal quantile: 1.96 for 95%."""
    return NormalDist().inv_cdf(0.5 + level / 2)


def wilson_interval(successes: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Unlike the textbook p +/- z*sqrt(p(1-p)/n), it never leaves [0, 1] and stays sensible for
    small n and for rates near 0 or 1 (where eval pass rates often live).
    """
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be in [0, n], got {successes} of {n}")
    z = z_value(level)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return low, high


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    return sorted_values[int(q * (len(sorted_values) - 1))]


def percentile(values: Sequence[float], q: float) -> float:
    """The q-quantile (0 <= q <= 1) by linear interpolation between order statistics (the same
    rule as numpy's default), e.g. percentile(latencies, 0.95) for p95."""
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0, 1]")
    xs = sorted(values)
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def bootstrap_ci[T](
    data: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    draws: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """(point estimate, low, high): a percentile bootstrap interval for any statistic.

    Resample the cases with replacement `draws` times, recompute the statistic, and take the middle
    `level` share of the results. Resample the unit you sampled: queries, not individual runs.
    """
    rng = random.Random(seed)
    n = len(data)
    samples = sorted(statistic([data[rng.randrange(n)] for _ in range(n)]) for _ in range(draws))
    alpha = (1 - level) / 2
    return statistic(data), _percentile(samples, alpha), _percentile(samples, 1 - alpha)


def pass_rate(outcomes: Sequence[bool]) -> float:
    return sum(outcomes) / len(outcomes) if outcomes else float("nan")


# --- Judge error (module 5) --------------------------------------------------------------------------


def corrected_pass_rate(p_observed: float, tpr: float, tnr: float) -> float:
    """Rogan-Gladen: the true pass rate implied by a judge's observed pass rate.

    observed = true * TPR + (1 - true) * (1 - TNR)   =>   true = (observed + TNR - 1) / (TPR + TNR - 1)

    Clipped to [0, 1]. Undefined when TPR + TNR <= 1 (the judge is no better than chance). nan when
    TPR or TNR is nan (no positives or no negatives to estimate it from).
    """
    if math.isnan(tpr) or math.isnan(tnr):
        return float("nan")
    denom = tpr + tnr - 1
    if denom <= 0:
        raise ValueError(f"TPR + TNR must exceed 1 (got {tpr:.2f} + {tnr:.2f})")
    return min(1.0, max(0.0, (p_observed + tnr - 1) / denom))


def observed_pass_rate(true_rate: float, tpr: float, tnr: float) -> float:
    """What a judge with this TPR and TNR reports when the true pass rate is `true_rate`."""
    return true_rate * tpr + (1 - true_rate) * (1 - tnr)


@dataclass(frozen=True)
class Estimate:
    observed: float
    corrected: float
    low: float
    high: float
    n_unlabelled: int
    n_labelled: int
    draws: int

    def __str__(self) -> str:
        return (
            f"observed pass rate {self.observed:.3f} on {self.n_unlabelled} unlabelled traces; "
            f"corrected {self.corrected:.3f}, 95% CI [{self.low:.3f}, {self.high:.3f}] "
            f"({self.draws} bootstrap draws, judge error from {self.n_labelled} labelled traces)"
        )


def bootstrap_corrected(
    labelled: list[tuple[bool, bool]],
    unlabelled: list[bool],
    draws: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> Estimate:
    """Corrected pass rate with a percentile bootstrap interval.

    `labelled` is (human_pass, judge_pass) on a held-out labelled set (the test split): it estimates
    the judge's TPR and TNR. `unlabelled` is the judge's verdicts on the traffic you want to measure.
    Both are resampled with replacement in every draw, so the interval includes uncertainty about the
    judge as well as about the traffic. Draws where TPR + TNR <= 1 are skipped and counted.
    When no draw is usable (for example the labelled set has no failures, so TNR is 0/0), the
    interval is undefined: low and high are nan and draws is 0.
    """

    def tpr_tnr(pairs: list[tuple[bool, bool]]) -> tuple[float, float]:
        pos = [j for h, j in pairs if h]
        neg = [j for h, j in pairs if not h]
        if not pos or not neg:
            return float("nan"), float("nan")
        return sum(pos) / len(pos), sum(not j for j in neg) / len(neg)

    p_obs = sum(unlabelled) / len(unlabelled)
    tpr, tnr = tpr_tnr(labelled)
    point = corrected_pass_rate(p_obs, tpr, tnr)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        lab = [labelled[rng.randrange(len(labelled))] for _ in labelled]
        unl = [unlabelled[rng.randrange(len(unlabelled))] for _ in unlabelled]
        t1, t0 = tpr_tnr(lab)
        if not (t1 + t0 > 1):  # nan or a useless judge in this resample
            continue
        samples.append(corrected_pass_rate(sum(unl) / len(unl), t1, t0))
    samples.sort()
    if not samples:
        nan = float("nan")
        return Estimate(p_obs, point, nan, nan, len(unlabelled), len(labelled), 0)
    alpha = (1 - level) / 2
    lo = samples[int(alpha * (len(samples) - 1))]
    hi = samples[int((1 - alpha) * (len(samples) - 1))]
    return Estimate(p_obs, point, lo, hi, len(unlabelled), len(labelled), len(samples))


# --- Prediction-powered inference (PPI, PPI++) ----------------------------------------------------------


@dataclass(frozen=True)
class PPIEstimate:
    estimate: float
    low: float
    high: float
    lam: float  # 1.0 is plain PPI; PPI++ tunes it (0 ignores the judge entirely)
    n_labelled: int
    n_unlabelled: int

    def __str__(self) -> str:
        kind = "PPI" if self.lam == 1.0 else f"PPI++ (lambda {self.lam:.2f})"
        return (
            f"{kind}: {self.estimate:.3f} [{self.low:.3f}, {self.high:.3f}] "
            f"from {self.n_labelled} human labels and {self.n_unlabelled} judge-only verdicts"
        )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _var(xs: list[float]) -> float:
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1) if len(xs) > 1 else 0.0


def ppi_mean(
    labelled: list[tuple[bool, bool]],
    unlabelled: list[bool],
    level: float = 0.95,
    tune: bool = True,
) -> PPIEstimate:
    """Prediction-powered estimate of a pass rate (Angelopoulos et al., 2023; PPI++ 2024).

    `labelled` is (human_pass, judge_pass) on a small set that a person labelled, drawn at random
    from the SAME traffic as `unlabelled`, the judge's verdicts on everything else. The judge's mean
    on the large set is corrected by the average human-minus-judge difference on the small one:

        estimate = mean(human_lab) + lam * (mean(judge_unl) - mean(judge_lab))

    With lam = 1 this is plain PPI. With `tune`, lam is chosen to minimise the variance (PPI++), so
    a judge that agrees with people narrows the interval and a useless one is down-weighted toward 0,
    where the estimate is just the human labels' mean: never worse than ignoring the judge. The
    interval is the normal approximation, clipped to [0, 1]. Unlike the Rogan-Gladen correction it
    needs no TPR + TNR > 1, and it stays well behaved with few labelled failures.
    """
    n, big_n = len(labelled), len(unlabelled)
    h = [float(a) for a, _ in labelled]
    f_lab = [float(b) for _, b in labelled]
    f_unl = [float(b) for b in unlabelled]
    lam = 1.0
    if tune:
        mh, mf = _mean(h), _mean(f_lab)
        cov = sum((a - mh) * (b - mf) for a, b in zip(h, f_lab, strict=True)) / max(n - 1, 1)
        var_f = (_var(f_lab) * (n - 1) + _var(f_unl) * (big_n - 1)) / max(n + big_n - 2, 1)
        lam = 0.0 if var_f == 0 else min(1.0, max(0.0, cov / ((1 + n / big_n) * var_f)))
    est = _mean(h) + lam * (_mean(f_unl) - _mean(f_lab))
    resid = [a - lam * b for a, b in zip(h, f_lab, strict=True)]
    se = math.sqrt(_var(resid) / n + lam**2 * _var(f_unl) / big_n)
    z = NormalDist().inv_cdf(0.5 + level / 2)
    return PPIEstimate(
        min(1.0, max(0.0, est)), max(0.0, est - z * se), min(1.0, est + z * se), lam, n, big_n
    )


# --- Paired comparisons -------------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedResult:
    """B minus A on the same cases. `b_only`: cases only B passes; `a_only`: only A passes."""

    n: int
    rate_a: float
    rate_b: float
    a_only: int
    b_only: int
    low: float
    high: float
    p_value: float

    @property
    def diff(self) -> float:
        return self.rate_b - self.rate_a

    def __str__(self) -> str:
        return (
            f"n={self.n}  A {self.rate_a:.3f}  B {self.rate_b:.3f}  diff {self.diff:+.3f} "
            f"95% CI [{self.low:+.3f}, {self.high:+.3f}]  "
            f"discordant: only A {self.a_only}, only B {self.b_only}  McNemar p={self.p_value:.3f}"
        )


def mcnemar_exact(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar test: are the discordant pairs split more unevenly than a fair coin?

    Only cases where A and B disagree carry information about which is better.
    """
    m = a_only + b_only
    if m == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(m, i) for i in range(k + 1)) / 2**m
    return min(1.0, 2 * tail)


def paired_bootstrap_diff(
    a: Sequence[bool],
    b: Sequence[bool],
    draws: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> PairedResult:
    """Compare two variants run on the same cases: resample cases (keeping each pair together)."""
    if len(a) != len(b) or not a:
        raise ValueError("a and b must be non-empty and the same length (one entry per case)")
    pairs = list(zip(a, b, strict=True))
    _, lo, hi = bootstrap_ci(
        pairs, lambda ps: sum(y for _, y in ps) / len(ps) - sum(x for x, _ in ps) / len(ps),
        draws=draws, seed=seed, level=level,
    )  # fmt: skip
    a_only = sum(1 for x, y in pairs if x and not y)
    b_only = sum(1 for x, y in pairs if y and not x)
    return PairedResult(
        len(pairs),
        pass_rate(a),
        pass_rate(b),
        a_only,
        b_only,
        lo,
        hi,
        mcnemar_exact(a_only, b_only),
    )


def holm(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values: compare each with alpha as usual afterwards.

    Controls the chance of any false positive across the whole family of tests (slices, failure
    modes, metrics) without being as blunt as plain Bonferroni.
    """
    order = sorted(p_values, key=p_values.get)
    m = len(order)
    out: dict[str, float] = {}
    running = 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (m - i) * p_values[key]))
        out[key] = running
    return out


# --- Repeated runs ----------------------------------------------------------------------------------


def pass_at_k(n: int, c: int, k: int) -> float:
    """Chance that at least one of k runs passes, estimated from c passes in n runs (unbiased)."""
    if k > n:
        raise ValueError("k cannot exceed the number of runs")
    if n - c < k:
        return 1.0
    return 1 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k: chance that all k runs pass, estimated from c passes in n runs (unbiased).

    The reliability view: a user who asks the same thing k times gets a good answer every time.
    """
    if k > n:
        raise ValueError("k cannot exceed the number of runs")
    return math.comb(c, k) / math.comb(n, k)


@dataclass(frozen=True)
class TrialSummary:
    n_cases: int
    n_trials: int
    run_rates: tuple[float, ...]  # pass rate of each full run over all cases
    always_pass: int  # cases that passed every trial
    never_pass: int  # cases that failed every trial

    @property
    def mean_rate(self) -> float:
        return mean(self.run_rates)

    @property
    def run_sd(self) -> float:
        return pstdev(self.run_rates)

    @property
    def flaky(self) -> int:
        return self.n_cases - self.always_pass - self.never_pass

    def __str__(self) -> str:
        rates = ", ".join(f"{r:.3f}" for r in self.run_rates)
        return (
            f"{self.n_cases} cases x {self.n_trials} runs: run pass rates {rates} "
            f"(mean {self.mean_rate:.3f}, sd {self.run_sd:.3f}); "
            f"always pass {self.always_pass}, never pass {self.never_pass}, flaky {self.flaky}"
        )


def trial_summary(outcomes: Mapping[str, Sequence[bool]]) -> TrialSummary:
    """`outcomes[case]` holds one boolean per run, in run order; every case needs the same count."""
    counts = {len(v) for v in outcomes.values()}
    if len(counts) != 1:
        raise ValueError("every case needs the same number of runs")
    k = counts.pop()
    rates = tuple(sum(v[t] for v in outcomes.values()) / len(outcomes) for t in range(k))
    return TrialSummary(
        len(outcomes),
        k,
        rates,
        sum(all(v) for v in outcomes.values()),
        sum(not any(v) for v in outcomes.values()),
    )


# --- Sample sizes -------------------------------------------------------------------------------------


def n_for_halfwidth(p: float, halfwidth: float, level: float = 0.95) -> int:
    """Cases needed so a pass-rate interval is about +/- `halfwidth` wide (normal approximation)."""
    z = z_value(level)
    return math.ceil(z * z * p * (1 - p) / halfwidth**2)


def n_two_proportions(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Cases per variant to detect p1 vs p2 with independent samples (two-sided z test)."""
    za, zb = z_value(1 - alpha), NormalDist().inv_cdf(power)
    pbar = (p1 + p2) / 2
    num = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(num**2 / (p1 - p2) ** 2)


def n_paired(discordant: float, diff: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Cases to detect a difference `diff` when both variants run on the same cases (McNemar).

    `discordant` is the expected share of cases where the two variants disagree (only-A plus
    only-B); you can estimate it from a pilot run. Connor (1987)'s approximation.
    """
    if not 0 < abs(diff) < discordant <= 1:
        raise ValueError("need 0 < |diff| < discordant <= 1")
    za, zb = z_value(1 - alpha), NormalDist().inv_cdf(power)
    num = za * math.sqrt(discordant) + zb * math.sqrt(discordant - diff**2)
    return math.ceil(num**2 / diff**2)


def _solve_mdd(n_needed: Callable[[float], int], n: int, hi: float) -> float:
    lo_d, hi_d = 1e-4, hi
    if n_needed(hi_d) > n:
        return float("nan")  # even the largest difference considered needs more than n
    for _ in range(60):
        mid = (lo_d + hi_d) / 2
        if n_needed(mid) > n:
            lo_d = mid
        else:
            hi_d = mid
    return hi_d


def mdd_two_proportions(n: int, p: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest improvement over a base pass rate `p` that n cases per variant can detect."""
    return _solve_mdd(lambda d: n_two_proportions(p, p + d, alpha, power), n, (1 - p) - 1e-9)


def mdd_paired(n: int, discordant: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest paired difference n shared cases can detect, given the discordant share."""
    return _solve_mdd(lambda d: n_paired(discordant, d, alpha, power), n, discordant - 1e-9)
