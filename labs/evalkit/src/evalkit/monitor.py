"""Production monitoring (module 9): sampling, drift statistics, control charts, and CUSUM.

    stable_fraction    where a key falls in [0, 1): the same key always gets the same draw
    random_sample      keep each key with probability `rate` (hash-based, reproducible)
    stratified_sample  the first k keys per stratum in hash order
    build_queue        random + stratified + signal-triggered picks, with inclusion probabilities
    weighted_rate      Hajek (ratio Horvitz-Thompson) estimate from a sample with known probabilities
    psi                population stability index between two category distributions
    new_categories     values that never appeared in the reference window
    p_chart            per-period proportions with 3-sigma limits around a reference rate
    bernoulli_cusum    one-sided CUSUM that alarms when a failure rate rises from p0 towards p1
    two_proportion_z   before/after comparison, for example around a model version change

Everything is plain Python and deterministic: hashing replaces random number generators, so the
same traffic always produces the same sample and the same alarms.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

# --- Sampling -----------------------------------------------------------------------------------


def stable_fraction(key: str, salt: str = "") -> float:
    """A number in [0, 1) derived from SHA-256 of `salt:key`. Sampling on it is reproducible and
    consistent: every service that sees the same request id makes the same keep/drop decision."""
    digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def random_sample(keys: Iterable[str], rate: float, salt: str = "random") -> list[str]:
    """Each key independently, with probability `rate`."""
    return [k for k in keys if stable_fraction(k, salt) < rate]


def stratified_sample(
    strata: Mapping[str, str], per_stratum: int, salt: str = "stratified"
) -> dict[str, float]:
    """{key: inclusion probability} for the first `per_stratum` keys of every stratum, in hash
    order. Small strata are taken whole (probability 1); large ones get k / N."""
    groups: dict[str, list[str]] = {}
    for k, s in strata.items():
        groups.setdefault(s, []).append(k)
    out = {}
    for members in groups.values():
        members.sort(key=lambda k: stable_fraction(k, salt))
        p = min(1.0, per_stratum / len(members))
        for k in members[:per_stratum]:
            out[k] = p
    return out


@dataclass(frozen=True)
class Pick:
    """One item in a review queue: why it was picked, and how likely it was to be picked at all."""

    key: str
    reasons: tuple[str, ...]
    prob: float

    @property
    def triggered(self) -> bool:
        return any(r.startswith("signal:") for r in self.reasons)


def build_queue(
    keys: Sequence[str],
    signals: Mapping[str, Sequence[str]] | None = None,
    strata: Mapping[str, str] | None = None,
    rate: float = 0.1,
    per_stratum: int = 0,
    signal_order: Sequence[str] = (),
    salt: str = "queue",
) -> list[Pick]:
    """A review queue from three designs at once:

    random       every key with probability `rate`
    stratified   up to `per_stratum` keys from every stratum (rare topics get seen)
    signal       every key with at least one signal (thumbs-down, retry, tool error, ...)

    The inclusion probability of a key is 1 if it carries a signal, otherwise
    1 - (1 - rate)(1 - p_stratum); the two hash draws use different salts, so they are independent.
    Order: signal-triggered first (by the first signal's position in `signal_order`), then the rest
    in hash order, which is as good as shuffled and stable across runs.
    """
    signals = signals or {}
    use_strata = bool(strata and per_stratum)
    strat = stratified_sample(strata, per_stratum, salt + ":s") if use_strata else {}
    size = Counter(strata.values()) if use_strata else Counter()  # type: ignore[union-attr]
    picks = []
    for k in keys:
        sig = list(signals.get(k, ()))
        reasons = [f"signal:{s}" for s in sig]
        if stable_fraction(k, salt + ":r") < rate:
            reasons.append("random")
        if k in strat:
            reasons.append(f"stratum:{strata[k]}")  # type: ignore[index]
        if not reasons:
            continue
        p_strat = min(1.0, per_stratum / size[strata[k]]) if use_strata else 0.0  # type: ignore[index]
        p = 1.0 if sig else 1 - (1 - rate) * (1 - p_strat)
        picks.append(Pick(k, tuple(reasons), p))
    rank = {s: i for i, s in enumerate(signal_order)}

    def order(p: Pick) -> tuple[int, int, float]:
        sig = [r[7:] for r in p.reasons if r.startswith("signal:")]
        first = min((rank.get(s, len(rank)) for s in sig), default=len(rank) + 1)
        return (0 if sig else 1, first, stable_fraction(p.key, salt + ":o"))

    return sorted(picks, key=order)


def weighted_rate(values: Mapping[str, bool], probs: Mapping[str, float]) -> float:
    """Hajek estimator: sum(v / p) / sum(1 / p). Weighting by 1 / inclusion probability undoes the
    over-representation of items a signal pulled into the sample."""
    num = sum(float(v) / probs[k] for k, v in values.items())
    den = sum(1.0 / probs[k] for k in values)
    return num / den if den else float("nan")


# --- Drift --------------------------------------------------------------------------------------


def proportions(values: Iterable[str]) -> dict[str, float]:
    c = Counter(values)
    n = sum(c.values())
    return {k: v / n for k, v in c.items()} if n else {}


def psi(reference: Iterable[str], current: Iterable[str], eps: float = 1e-4) -> float:
    """Population stability index: sum over categories of (cur - ref) * ln(cur / ref).

    0 means identical mixes. A common rule of thumb reads < 0.1 as stable, 0.1 to 0.25 as a
    moderate shift, and > 0.25 as a large one. Empty categories are floored at `eps`."""
    ref, cur = proportions(reference), proportions(current)
    total = 0.0
    for k in set(ref) | set(cur):
        r, c = max(ref.get(k, 0.0), eps), max(cur.get(k, 0.0), eps)
        total += (c - r) * math.log(c / r)
    return total


def new_categories(reference: Iterable[str], current: Iterable[str]) -> list[str]:
    """Values in `current` that never appeared in `reference` (a new device, app version, language)."""
    seen = set(reference)
    return sorted({v for v in current if v not in seen})


@dataclass(frozen=True)
class ChartPoint:
    label: str
    n: int
    x: int
    rate: float
    lcl: float
    ucl: float

    @property
    def status(self) -> str:
        if self.n == 0:
            return "empty"
        if self.rate > self.ucl:
            return "high"
        if self.rate < self.lcl:
            return "low"
        return "ok"


def p_chart(
    p0: float, periods: Sequence[tuple[str, int, int]], sigmas: float = 3.0
) -> list[ChartPoint]:
    """A p-chart: (label, n, failures) per period against a reference rate p0. The limits widen
    for small periods (weekends, the night) because they depend on each period's n."""
    out = []
    for label, n, x in periods:
        half = sigmas * math.sqrt(p0 * (1 - p0) / n) if n else 0.0
        out.append(
            ChartPoint(
                label, n, x, x / n if n else float("nan"), max(0.0, p0 - half), min(1.0, p0 + half)
            )
        )
    return out


@dataclass
class Cusum:
    p0: float
    p1: float
    h: float
    path: list[float] = field(default_factory=list)
    alarm_at: int | None = None  # index of the first observation where the sum reached h

    @property
    def weights(self) -> tuple[float, float]:
        """(added on a failure, added on a success): log-likelihood ratios of p1 against p0."""
        return math.log(self.p1 / self.p0), math.log((1 - self.p1) / (1 - self.p0))


def bernoulli_cusum(failures: Sequence[bool], p0: float, p1: float, h: float = 4.0) -> Cusum:
    """One-sided Bernoulli CUSUM (Page, 1954) for a rise in a failure rate from p0 to p1.

    S_t = max(0, S_{t-1} + w), with w = ln(p1/p0) on a failure and ln((1-p1)/(1-p0)) on a success.
    Successes pull the sum back towards 0, failures push it up; it alarms when S_t >= h. A larger
    h means fewer false alarms and a longer delay before a real shift is caught.
    """
    if not 0 < p0 < p1 < 1:
        raise ValueError("need 0 < p0 < p1 < 1")
    c = Cusum(p0, p1, h)
    up, down = c.weights
    s = 0.0
    for i, f in enumerate(failures):
        s = max(0.0, s + (up if f else down))
        c.path.append(s)
        if c.alarm_at is None and s >= h:
            c.alarm_at = i
    return c


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float, float]:
    """(p2 - p1, z, two-sided p) for two independent proportions, pooled standard error."""
    p1, p2 = x1 / n1, x2 / n2
    pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return p2 - p1, 0.0, 1.0
    z = (p2 - p1) / se
    return p2 - p1, z, 2 * _norm_sf(abs(z))
