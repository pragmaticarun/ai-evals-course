"""Regression gates for CI (module 8): may this change merge, judging by paired eval outcomes?

A gate compares a candidate run with a baseline run on the same cases, one metric at a time. Each
metric is a pass/fail outcome per case (True = PASS), so the comparison is paired (module 6):

    FAIL  the candidate is worse, and not by chance: the McNemar p-value (Holm-adjusted across the
          gate's metrics) is below `alpha` and the drop is at least `min_effect`
    WARN  not shown to be worse, but the interval cannot rule out a drop bigger than `margin`
          (too few cases, or too many flips in both directions, to say "no regression")
    PASS  otherwise

There is no fixed "pass rate must be at least X" rule. A fixed threshold flakes when the true rate sits
near it, and it waves through real drops that happen to stay above it.

Budgets: `Usage` adds up calls, tokens, cost, and recorded latency; `budget_problems` checks a suite
against a `Budget` for the replay job and for re-recording it live.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from evalkit.stats import PairedResult, holm, paired_bootstrap_diff


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


_ORDER = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}
ICON = {Status.PASS: "✅", Status.WARN: "⚠️", Status.FAIL: "❌"}


@dataclass(frozen=True)
class GateRule:
    alpha: float = 0.05  # two-sided significance level for "worse, not by chance"
    margin: float = 0.05  # the smallest drop you would care about (WARN if it cannot be ruled out)
    min_effect: float = 0.0  # ignore significant drops smaller than this (absolute rate)
    adjust: str = "holm"  # "holm" or "none": several metrics are several chances to cry wolf
    draws: int = 2000
    seed: int = 0
    level: float = 0.95


@dataclass(frozen=True)
class MetricGate:
    metric: str
    result: PairedResult
    p_adjusted: float
    status: Status
    reason: str
    dropped: int = 0  # cases without an outcome on one side (not applicable, or unparsed)


@dataclass
class GateResult:
    rule: GateRule
    metrics: list[MetricGate] = field(default_factory=list)

    @property
    def status(self) -> Status:
        return max((m.status for m in self.metrics), key=_ORDER.__getitem__, default=Status.PASS)

    @property
    def blocked(self) -> bool:
        return self.status is Status.FAIL

    def markdown(self) -> str:
        lines = [
            "| Metric | n | Base | Head | Head − base (95% CI) | Flips −/+ | p (adj.) | Gate |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for m in self.metrics:
            r = m.result
            lines.append(
                f"| {m.metric} | {r.n} | {r.rate_a:.3f} | {r.rate_b:.3f} | "
                f"{r.diff:+.3f} [{r.low:+.3f}, {r.high:+.3f}] | {r.a_only}/{r.b_only} | "
                f"{fmt_p(m.p_adjusted)} | {ICON[m.status]} {m.status.value} |"
            )
        return "\n".join(lines)


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def paired_outcomes(
    base: Mapping[str, bool | None], head: Mapping[str, bool | None]
) -> tuple[list[str], list[bool], list[bool], int]:
    """Cases with an outcome on both sides, in sorted order; and how many were dropped."""
    keys = sorted(set(base) | set(head))
    ids = [k for k in keys if base.get(k) is not None and head.get(k) is not None]
    return ids, [bool(base[k]) for k in ids], [bool(head[k]) for k in ids], len(keys) - len(ids)


def flips(
    base: Mapping[str, bool | None], head: Mapping[str, bool | None]
) -> tuple[list[str], list[str]]:
    """(newly failing, newly passing) case ids: the cases a reviewer should read first."""
    ids, a, b, _ = paired_outcomes(base, head)
    lost = [i for i, x, y in zip(ids, a, b, strict=True) if x and not y]
    gained = [i for i, x, y in zip(ids, a, b, strict=True) if y and not x]
    return lost, gained


def evaluate_gate(
    metrics: Mapping[str, tuple[Mapping[str, bool | None], Mapping[str, bool | None]]],
    rule: GateRule | None = None,
) -> GateResult:
    """Gate every metric: {name: (baseline outcomes, candidate outcomes)} keyed by case id."""
    rule = rule or GateRule()
    results: dict[str, tuple[PairedResult, int]] = {}
    for name, (base, head) in metrics.items():
        ids, a, b, dropped = paired_outcomes(base, head)
        if not ids:
            raise ValueError(f"metric {name!r} has no case with an outcome on both sides")
        results[name] = (
            paired_bootstrap_diff(a, b, draws=rule.draws, seed=rule.seed, level=rule.level),
            dropped,
        )
    raw = {name: r.p_value for name, (r, _) in results.items()}
    adjusted = holm(raw) if rule.adjust == "holm" else raw
    out = GateResult(rule)
    for name, (r, dropped) in results.items():
        p = adjusted[name]
        if r.diff < 0 and p < rule.alpha and -r.diff >= rule.min_effect:
            status, reason = Status.FAIL, "worse, and not by chance"
        elif r.low < -rule.margin:
            status, reason = Status.WARN, f"cannot rule out a drop larger than {rule.margin:.2f}"
        elif r.diff > 0 and p < rule.alpha:
            status, reason = Status.PASS, "better, and not by chance"
        else:
            status, reason = Status.PASS, "no regression detected"
        out.metrics.append(MetricGate(name, r, p, status, reason, dropped))
    return out


def naive_gate(base_rate: float, head_rate: float, tolerance: float = 0.0) -> Status:
    """The rule this module argues against: block when the head's rate drops by more than a tolerance."""
    return Status.FAIL if head_rate < base_rate - tolerance else Status.PASS


# --- Budgets -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    """What a suite costs to (re-)record live, read from the recorded responses."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0  # sum of recorded call latencies: serial wall time of a live run

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.calls + other.calls,
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cost_usd + other.cost_usd,
            self.latency_s + other.latency_s,
        )

    def live_minutes(self, concurrency: int = 1) -> float:
        return self.latency_s / max(1, concurrency) / 60

    def as_dict(self) -> dict[str, float | int]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "latency_s": round(self.latency_s, 1),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, float | int]) -> Usage:
        return cls(
            int(d.get("calls", 0)),
            int(d.get("input_tokens", 0)),
            int(d.get("output_tokens", 0)),
            float(d.get("cost_usd", 0.0)),
            float(d.get("latency_s", 0.0)),
        )


@dataclass(frozen=True)
class Budget:
    replay_seconds: float = 120.0  # the PR job's eval step, in replay mode
    live_usd: float = 2.0  # one live re-record of the suite
    live_minutes: float = 30.0  # wall time of that re-record at `concurrency`
    concurrency: int = 4


def budget_problems(budget: Budget, replay_seconds: float, live: Usage) -> list[str]:
    problems = []
    if replay_seconds > budget.replay_seconds:
        problems.append(
            f"replay took {replay_seconds:.1f} s (budget {budget.replay_seconds:.0f} s)"
        )
    if live.cost_usd > budget.live_usd:
        problems.append(
            f"a live re-record would cost ${live.cost_usd:.2f} (budget ${budget.live_usd:.2f})"
        )
    minutes = live.live_minutes(budget.concurrency)
    if minutes > budget.live_minutes:
        problems.append(
            f"a live re-record would take {minutes:.1f} min at concurrency {budget.concurrency} "
            f"(budget {budget.live_minutes:.0f} min)"
        )
    return problems


def describe(results: Sequence[MetricGate]) -> list[str]:
    """One line per metric that did not pass, for logs and commit messages."""
    return [
        f"{m.metric}: {m.result.diff:+.3f} [{m.result.low:+.3f}, {m.result.high:+.3f}], "
        f"p(adj.)={fmt_p(m.p_adjusted)}: {m.reason}"
        for m in results
        if m.status is not Status.PASS
    ]
