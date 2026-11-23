"""Module 11 lab: improving MediaDoctor with evidence (accuracy, latency, and cost).

    uv run mediadoctor-lab11 ev                             # what to fix first: expected value of fixing
    uv run mediadoctor-lab11 variants                       # the configurations and their one change
    uv run mediadoctor-lab11 run VARIANT                    # replay one configuration on dev, per task
    uv run mediadoctor-lab11 report [--out FILE]            # success CI, p50/p95, cost per (successful) task
    uv run mediadoctor-lab11 pareto [--svg FILE]            # the accuracy vs cost frontier
    uv run mediadoctor-lab11 latency VARIANT [--vs PARENT]  # where the time goes, and which tasks slowed
    uv run mediadoctor-lab11 trace VARIANT CASE             # one task's span tree, with timings
    uv run mediadoctor-lab11 cost [--runs N]                # what re-running the dev suite live costs
    uv run mediadoctor-lab11 log [--out FILE]               # the experiment log, pre-registered + measured
    uv run mediadoctor-lab11 memo [--out FILE]              # a draft one-page decision memo
    uv run mediadoctor-lab11 confirm VARIANT [--release]    # the held-out check (logged, once)

Everything replays from fixtures (namespaces mediadoctor-m11-*) and needs no API key. The model's
behaviour, token counts, and latencies are synthetic-authored (scripts/author_module11_fixtures.py);
the agent loop, tools, checks, prices (config/models.toml), and statistics are real code.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import sys
import tomllib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import repo_root
from evalkit.golden import HoldoutAccessError, HoldoutGuard
from evalkit.stats import (
    PairedResult,
    bootstrap_ci,
    mdd_paired,
    paired_bootstrap_diff,
    percentile,
    wilson_interval,
)
from evalkit.viewer import render_tree
from mediadoctor import experiments as X

RUNS = Path("runs") / "m11"


# --- Configuration --------------------------------------------------------------------------------------


@cache
def prereg() -> dict[str, Any]:
    path = repo_root() / "config" / "experiments" / "preregistration.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


@cache
def log_entries() -> list[dict[str, Any]]:
    path = repo_root() / "config" / "experiments" / "log.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["experiment"]


def timeout_ms() -> float:
    return float(prereg()["guardrails"]["timeout_ms"])


def margin() -> float:
    return float(prereg()["metric"]["non_inferiority_margin"])


def split_cases(split: str) -> list[dict[str, Any]]:
    """split: "dev" (the pre-registered dev splits) or "holdout"."""
    s = prereg()["study"]
    want = set(s["dev_splits"]) if split == "dev" else {s["holdout_split"]}
    return [c for c in X.cases() if c["split"] in want]


def holdout_guard() -> HoldoutGuard:
    return HoldoutGuard(holdout=frozenset(c["id"] for c in split_cases("holdout")))


# --- 1. What to fix: expected value -------------------------------------------------------------------

P_FIX = {"easy": 0.8, "medium": 0.6, "hard": 0.3}  # chance one attempt removes most of the mode
EFFORT_DAYS = {"easy": 1, "medium": 3, "hard": 8}


@dataclass(frozen=True)
class FixValue:
    mode: str
    count: int
    n: int
    severity: int
    fixability: str

    @property
    def rate(self) -> float:
        return self.count / self.n

    @property
    def ci(self) -> tuple[float, float]:
        return wilson_interval(self.count, self.n)

    @property
    def value(self) -> float:
        """Expected severity-weighted failures removed per 100 tasks."""
        return 100 * self.rate * self.severity * P_FIX[self.fixability]

    @property
    def per_day(self) -> float:
        return self.value / EFFORT_DAYS[self.fixability]


def fix_values() -> list[FixValue]:
    root = repo_root() / "data" / "labels"
    modes = tomllib.loads((root / "module03_modes.toml").read_text(encoding="utf-8"))["mode"]
    with (root / "module03_reference.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    counts = Counter(m for r in rows for m in r["modes"].split(";") if m)
    out = [
        FixValue(m["id"], counts[m["id"]], len(rows), m["severity"], m["fixability"]) for m in modes
    ]
    return sorted(out, key=lambda f: -f.value)


def ev_text() -> str:
    lines = [
        "Expected value of fixing each failure mode (module 3 reference labels, n=100 traces)",
        "  value = rate x severity x P(fix works), per 100 tasks;  per day = value / effort days",
        f"  P(fix): {P_FIX}   effort days: {EFFORT_DAYS}",
        "",
        f"  {'mode':24s} {'rate':>5s} {'95% CI':>13s} {'sev':>3s} {'fix':>6s} {'value':>6s} {'per day':>7s}",
    ]  # fmt: skip
    for f in fix_values():
        lo, hi = f.ci
        lines.append(
            f"  {f.mode:24s} {f.rate:5.2f} [{lo:.2f}, {hi:.2f}] {f.severity:3d} {f.fixability:>6s} "
            f"{f.value:6.1f} {f.per_day:7.1f}"
        )
    lines.append(
        "\nThe intervals overlap: n=100 ranks the big modes against the small ones, not the big "
        "ones against each other. Fix by value; break ties with effort."
    )
    return "\n".join(lines)


# --- 2. Running a configuration -----------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    case_id: str
    graded: bool  # all four checks pass
    timed_out: bool
    checks: tuple[tuple[str, bool], ...]
    cost_usd: float
    latency_ms: float
    calls: int
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    escalated: bool
    retried: bool

    @property
    def success(self) -> bool:
        return self.graded and not self.timed_out


def to_row(t: X.TaskResult) -> Row:
    u = t.usage
    return Row(
        t.case_id, t.graded_success, t.latency_ms > timeout_ms(), tuple(t.checks.items()),
        u.cost_usd, t.latency_ms, u.calls, u.input_tokens, u.output_tokens,
        u.cache_write_tokens, u.cache_read_tokens, t.escalated, t.retried,
    )  # fmt: skip


@cache
def task_results(variant: str, split: str = "dev") -> tuple[X.TaskResult, ...]:
    if split == "holdout":
        raise HoldoutAccessError("use confirm_holdout(): the held-out split is read once, logged")
    return tuple(X.run_task(c, variant) for c in split_cases(split))


@cache
def run_rows(variant: str, split: str = "dev") -> tuple[Row, ...]:
    return tuple(to_row(t) for t in task_results(variant, split))


@cache
def reference_labels() -> dict[tuple[str, str], str]:
    """(variant, case id) -> the failure mode in the final answer ("none" if correct), as authored."""
    path = repo_root() / "data" / "labels" / "module11_reference.csv"
    with path.open(encoding="utf-8") as fh:
        return {(r["variant"], r["case_id"]): r["mode"] for r in csv.DictReader(fh)}


LABEL_MODES = ("premise", "ignored", "skipped", "format")


def mode_counts(variant: str, split: str = "dev") -> Counter[str]:
    labels = reference_labels()
    return Counter(labels[(variant, c["id"])] for c in split_cases(split))


@dataclass(frozen=True)
class SelfCheck:
    tp: int  # defective first answer, judge said FAIL
    fn: int
    tn: int
    fp: int  # good first answer, judge said FAIL (a false alarm: a retry that cannot help)
    fixed: int  # retried tasks whose final answer is correct
    retried: int


def selfcheck_stats(split: str = "dev") -> SelfCheck:
    """The retry variant's judge against the reference labels of its first answers (= v3-cache's)."""
    labels = reference_labels()
    tp = fn = tn = fp = fixed = retried = 0
    for t in task_results("retry", split):
        bad = labels[("v3-cache", t.case_id)] != "none"
        failed = t.attempts[0].self_check is False
        tp, fn = tp + (bad and failed), fn + (bad and not failed)
        tn, fp = tn + (not bad and not failed), fp + (not bad and failed)
        if t.retried:
            retried += 1
            fixed += labels[("retry", t.case_id)] == "none"
    return SelfCheck(tp, fn, tn, fp, fixed, retried)


# --- 3. Metrics ---------------------------------------------------------------------------------------


def cost_per_success(rows: Sequence[Row]) -> float:
    ok = sum(r.success for r in rows)
    return sum(r.cost_usd for r in rows) / ok if ok else math.inf


@dataclass(frozen=True)
class Summary:
    variant: str
    n: int
    successes: int
    low: float
    high: float
    p50_ms: float
    p95_ms: float
    p95_low: float
    p95_high: float
    timeouts: int
    cost_per_task: float
    cost_per_success: float
    cps_low: float
    cps_high: float
    cache_hit_rate: float
    escalated: int
    retried: int

    @property
    def rate(self) -> float:
        return self.successes / self.n


def summarize(variant: str, rows: Sequence[Row]) -> Summary:
    n, ok = len(rows), sum(r.success for r in rows)
    lo, hi = wilson_interval(ok, n)
    lat = [r.latency_ms for r in rows]
    _, cps_lo, cps_hi = bootstrap_ci(list(rows), cost_per_success, draws=1000, seed=11)
    _, p95_lo, p95_hi = bootstrap_ci(lat, lambda xs: percentile(xs, 0.95), draws=1000, seed=11)
    cached = sum(r.cache_read_tokens for r in rows)
    all_in = sum(r.input_tokens + r.cache_read_tokens + r.cache_write_tokens for r in rows)
    return Summary(
        variant, n, ok, lo, hi, percentile(lat, 0.5), percentile(lat, 0.95), p95_lo, p95_hi,
        sum(r.timed_out for r in rows), sum(r.cost_usd for r in rows) / n,
        cost_per_success(rows), cps_lo, cps_hi, cached / all_in if all_in else 0.0,
        sum(r.escalated for r in rows), sum(r.retried for r in rows),
    )  # fmt: skip


@cache
def summary(variant: str) -> Summary:
    return summarize(variant, run_rows(variant))


def paired(a: str, b: str) -> PairedResult:
    """b minus a on dev success, same cases."""
    ra, rb = run_rows(a), run_rows(b)
    return paired_bootstrap_diff([r.success for r in ra], [r.success for r in rb], seed=11)


def meets_guardrails(s: Summary) -> list[str]:
    g = prereg()["guardrails"]
    broken = []
    if s.p95_ms > g["p95_latency_ms"]:
        broken.append(f"p95 {s.p95_ms / 1000:.1f} s > {g['p95_latency_ms'] / 1000:.0f} s")
    if s.cost_per_success > g["max_cost_per_success_usd"]:
        broken.append(f"cost/success ${s.cost_per_success:.4f} > ${g['max_cost_per_success_usd']}")
    return broken


def pareto_front(points: Sequence[Summary]) -> list[Summary]:
    """The variants no other variant beats on both cost per task (lower) and success (higher)."""

    def dominated(p: Summary) -> bool:
        return any(
            q.cost_per_task <= p.cost_per_task and q.rate >= p.rate
            and (q.cost_per_task < p.cost_per_task or q.rate > p.rate)
            for q in points
        )  # fmt: skip

    return sorted((p for p in points if not dominated(p)), key=lambda p: p.cost_per_task)


def cheapest_within(points: Sequence[Summary], points_of_best: float = 0.02) -> Summary:
    """The cheapest variant (cost per successful task) whose success is within `points_of_best` of
    the best point estimate. Point estimates only: see `decide` for the version with a CI."""
    best = max(p.rate for p in points)
    near = [p for p in points if p.rate >= best - points_of_best - 1e-12]
    return min(near, key=lambda p: p.cost_per_success)


@dataclass(frozen=True)
class Decision:
    chosen: str  # the recommendation
    best: str  # the highest dev success of any configuration meeting the guardrails
    kept: list[str]  # the release candidate's chain of kept changes
    verdicts: dict[str, tuple[str, str]]  # variant -> (keep | reject, why)


def decide() -> Decision:
    """Apply config/experiments/preregistration.toml's decision rule to the experiment log."""
    verdicts = {e["variant"]: verdict(e) for e in log_entries()}
    release = "v1"
    kept = [release]
    for e in log_entries():
        v = X.variants()[e["variant"]]
        if v.parent in kept and verdicts[v.name][0] == "keep":
            kept.append(v.name)
    chosen = max(kept, key=lambda n: (summary(n).rate, -summary(n).cost_per_success))
    ok = [n for n in X.variants() if not meets_guardrails(summary(n))]
    best = max(ok, key=lambda n: (summary(n).rate, -summary(n).cost_per_success))
    return Decision(chosen, best, kept, verdicts)


# --- 4. Reports ----------------------------------------------------------------------------------------


def money(x: float) -> str:
    return "inf" if math.isinf(x) else f"${x:.5f}"


def report_text(names: Sequence[str] | None = None) -> str:
    names = list(names or X.variants())
    vs = X.variants()
    n = len(split_cases("dev"))
    lines = [
        f"MediaDoctor configurations on dev (n={n}); success = all four checks pass within "
        f"{timeout_ms() / 1000:.0f} s",
        "",
        f"{'variant':9s} {'success':>7s} {'95% CI':>14s} {'p50 s':>6s} {'p95 s':>6s} {'95% CI':>12s} {'t/o':>3s} "
        f"{'cost/task':>10s} {'cost/success':>12s} {'95% CI':>21s} {'cache':>5s}",
    ]  # fmt: skip
    for name in names:
        s = summary(name)
        lines.append(
            f"{name:9s} {s.rate:7.3f} [{s.low:.3f}, {s.high:.3f}] {s.p50_ms / 1000:6.2f} "
            f"{s.p95_ms / 1000:6.2f} [{s.p95_low / 1000:4.1f}, {s.p95_high / 1000:4.1f}] "
            f"{s.timeouts:3d} {money(s.cost_per_task):>10s} "
            f"{money(s.cost_per_success):>12s} [{money(s.cps_low)}, {money(s.cps_high)}] "
            f"{s.cache_hit_rate:5.0%}"
        )
    lines += ["", "Each change against its parent (paired on the same cases, success):"]
    for name in names:
        v = vs[name]
        if v.parent and v.parent in names:
            p = paired(v.parent, name)
            a, b = summary(v.parent), summary(name)
            lines.append(
                f"  {name:9s} vs {v.parent:9s} {p.diff:+.3f} [{p.low:+.3f}, {p.high:+.3f}]  "
                f"only parent {p.a_only:2d}, only {name} {p.b_only:2d}  "
                f"cost/success {(b.cost_per_success / a.cost_per_success - 1):+.0%}  "
                f"p95 {(b.p95_ms - a.p95_ms) / 1000:+.2f} s   ({v.change})"
            )
    lines += ["", "Failure modes in the final answers (reference labels; dev):",
              f"  {'variant':9s} " + " ".join(f"{m:>8s}" for m in LABEL_MODES)]  # fmt: skip
    for name in names:
        mc = mode_counts(name)
        lines.append(f"  {name:9s} " + " ".join(f"{mc[m]:8d}" for m in LABEL_MODES))
    front = pareto_front([summary(x) for x in names])
    lines.append(
        "\nPareto frontier (cost per task vs success): " + " -> ".join(p.variant for p in front)
    )
    s = summary("cascade") if "cascade" in names else None
    if s:
        lines.append(f"Cascade escalated {s.escalated}/{s.n} tasks to Sonnet.")
    if "retry" in names:
        sc = selfcheck_stats()
        lines.append(
            f"Retry: the self-check sent {sc.retried}/{n} tasks back ({sc.tp} of {sc.tp + sc.fn} "
            f"defective answers caught, {sc.fp} false alarms on {sc.tn + sc.fp} good ones); "
            f"{sc.fixed} of the {sc.retried} retried tasks ended correct."
        )
    return "\n".join(lines)


def pareto_svg(names: Sequence[str] | None = None, width: int = 720, height: int = 440) -> str:
    """Success (with Wilson 95% CI whiskers) against cost per task on a log axis; the frontier joined."""
    names = list(names or X.variants())
    pts = [summary(n) for n in names]
    front = {p.variant for p in pareto_front(pts)}
    left, right, top, bottom = 70, 30, 40, 60
    cmin = min(p.cost_per_task for p in pts) / 1.6
    cmax = max(p.cost_per_task for p in pts) * 1.6
    ymin = max(0.0, math.floor((min(p.low for p in pts) - 0.03) * 20) / 20)
    ymax = min(1.0, math.ceil((max(p.high for p in pts) + 0.01) * 20) / 20)

    def x(c: float) -> float:
        return left + (math.log10(c) - math.log10(cmin)) / (math.log10(cmax) - math.log10(cmin)) * (
            width - left - right
        )  # noqa: E501

    def y(v: float) -> float:
        return top + (ymax - v) / (ymax - ymin) * (height - top - bottom)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="12">',
        "<title>MediaDoctor: success vs cost per task (dev)</title>",
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width / 2}" y="22" text-anchor="middle" font-size="14">'
        "Success vs cost per task (dev, 95% CI); the line joins the Pareto frontier</text>",
    ]
    for k in range(int(round(ymin * 20)), int(round(ymax * 20)) + 1):
        v = k / 20
        out.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#eee"/>'
        )  # noqa: E501
        out.append(f'<text x="{left - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.2f}</text>')
    decade = math.floor(math.log10(cmin))
    while 10**decade <= cmax:
        for m in (1, 2, 5):
            c = m * 10**decade
            if cmin <= c <= cmax:
                out.append(
                    f'<line x1="{x(c):.1f}" x2="{x(c):.1f}" y1="{top}" y2="{height - bottom}" stroke="#eee"/>'
                )  # noqa: E501
                out.append(
                    f'<text x="{x(c):.1f}" y="{height - bottom + 16}" text-anchor="middle">${c:g}</text>'
                )  # noqa: E501
        decade += 1
    out.append(f'<text x="{(left + width - right) / 2}" y="{height - 18}" text-anchor="middle">'
               "cost per task, USD (log scale)</text>")  # fmt: skip
    out.append(f'<text x="18" y="{(top + height - bottom) / 2}" text-anchor="middle" '
               f'transform="rotate(-90 18 {(top + height - bottom) / 2})">task success rate</text>')  # fmt: skip
    fr = sorted((p for p in pts if p.variant in front), key=lambda p: p.cost_per_task)
    path = " ".join(f"{x(p.cost_per_task):.1f},{y(p.rate):.1f}" for p in fr)
    out.append(f'<polyline points="{path}" fill="none" stroke="#2b6cb0" stroke-width="2"/>')
    for p in pts:
        cx, cy = x(p.cost_per_task), y(p.rate)
        colour = "#2b6cb0" if p.variant in front else "#888"
        out.append(
            f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(p.high):.1f}" y2="{y(p.low):.1f}" stroke="{colour}"/>'
        )  # noqa: E501
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{colour}"><title>'
                   f"{html.escape(p.variant)}: success {p.rate:.3f} [{p.low:.3f}, {p.high:.3f}], "
                   f"cost/task {money(p.cost_per_task)}, cost/success {money(p.cost_per_success)}"
                   "</title></circle>")  # fmt: skip
        crowded = any(0 < x(q.cost_per_task) - cx < 60 and abs(y(q.rate) - cy) < 45 for q in pts)
        tx, anchor = (cx - 8, "end") if crowded else (cx + 8, "start")
        out.append(f'<text x="{tx:.1f}" y="{cy - 6:.1f}" text-anchor="{anchor}" fill="{colour}">'
                   f"{html.escape(p.variant)}</text>")  # fmt: skip
    out.append("</svg>")
    return "\n".join(out) + "\n"


def spans_by_op(spans: list[dict[str, Any]]) -> dict[str, float]:
    """Milliseconds per kind of leaf work in one trace: agent calls, self-check calls, tools."""
    out: Counter[str] = Counter()
    for s in spans:
        a = s["attributes"]
        op = a.get("gen_ai.operation.name")
        ms = (s["end_time_unix_nano"] - s["start_time_unix_nano"]) / 1e6
        if op == "chat":
            out["self-check" if a.get("mediadoctor.self_check") else "agent calls"] += ms
        elif op == "execute_tool":
            out["tools"] += ms
    return dict(out)


def latency_text(variant: str, vs: str | None = None, top: int = 5) -> str:
    vs = vs or X.variants()[variant].parent
    lines = []
    for name in (vs, variant):
        s = summary(name)
        parts: Counter[str] = Counter()
        calls = 0
        for t in task_results(name):
            for a in t.attempts:
                parts.update(spans_by_op(a.spans))
            calls += t.usage.calls
        n = s.n
        lines.append(
            f"{name:9s} p50 {s.p50_ms / 1000:5.2f} s  p95 {s.p95_ms / 1000:5.2f} s  "
            f"calls/task {calls / n:4.2f}  mean ms/task: "
            + ", ".join(f"{k} {v / n:,.0f}" for k, v in sorted(parts.items()))
        )
    ra = {r.case_id: r for r in run_rows(vs)}
    deltas = sorted(((r.latency_ms - ra[r.case_id].latency_ms, r) for r in run_rows(variant)),
                    key=lambda d: -d[0])  # fmt: skip
    lines.append(f"\nTasks that slowed most ({variant} minus {vs}):")
    for d, r in deltas[:top]:
        why = "retried" if r.retried else "escalated" if r.escalated else f"{r.calls} calls"
        lines.append(f"  {r.case_id}  {d / 1000:+6.2f} s  ({ra[r.case_id].latency_ms / 1000:.2f} -> "
                     f"{r.latency_ms / 1000:.2f} s, {why})")  # fmt: skip
    return "\n".join(lines)


def cost_text(runs: int = 1, names: Sequence[str] | None = None) -> str:
    names = list(names or X.variants())
    n = len(split_cases("dev"))
    lines = [f"Re-running the dev suite live ({n} tasks x {runs} run(s)); Batch API = 50% off, "
             "results within 24 h, so for nightly evals, not for users:"]  # fmt: skip
    for name in names:
        total = summary(name).cost_per_task * n * runs
        lines.append(f"  {name:9s} standard ${total:7.3f}   batch ${total / 2:7.3f}")
    return "\n".join(lines)


def trace_text(variant: str, case_id: str) -> str:
    case = next(c for c in X.cases() if c["id"] == case_id)
    if case["split"] == prereg()["study"]["holdout_split"]:
        holdout_guard().check([case_id], "trace")
    t = X.run_task(case, variant)
    out = []
    for a in t.attempts:
        out.append(render_tree(a.spans, show_all=True))
    out.append(f"\nchecks: {t.checks}")
    out.append(f"latency {t.latency_ms / 1000:.2f} s  cost ${t.usage.cost_usd:.5f}  calls {t.usage.calls}  "
               f"cache read {t.usage.cache_read_tokens} / write {t.usage.cache_write_tokens} tokens")  # fmt: skip
    out.append(f"\nanswer:\n{t.answer}")
    return "\n".join(out)


# --- 5. Experiment log and decision memo ---------------------------------------------------------------


def verdict(entry: dict[str, Any]) -> tuple[str, str]:
    v = X.variants()[entry["variant"]]
    p = paired(v.parent, v.name)
    a, b = summary(v.parent), summary(v.name)
    cheaper = b.cost_per_success < a.cost_per_success
    if entry["kind"] == "superiority":
        ok = p.low > 0
        why = f"CI lower bound {p.low:+.3f} {'>' if ok else '<='} 0"
    elif entry["kind"] == "non-inferiority":
        ok = p.low > -margin() and cheaper
        rel = "above" if p.low > -margin() else "below"
        why = f"CI lower bound {p.low:+.3f} {rel} -{margin():.2f}; cost/success {'down' if cheaper else 'up'}"
    else:
        ga, gb = run_rows(v.parent), run_rows(v.name)
        same = [r.checks for r in ga] == [r.checks for r in gb]
        ok = same and cheaper and b.p95_ms <= a.p95_ms * 1.05
        why = (f"graded answers identical: {'yes' if same else 'NO'}; cost/success "
               f"{'down' if cheaper else 'up'}; p95 {'held' if b.p95_ms <= a.p95_ms * 1.05 else 'rose'}")  # fmt: skip
    broken = meets_guardrails(b)
    if broken:
        ok, why = False, why + "; guardrail: " + "; ".join(broken)
    return ("keep" if ok else "reject"), why


def log_markdown() -> str:
    pr = prereg()
    lines = [
        "# Experiment log: MediaDoctor cost, latency, and accuracy",
        "",
        f"Question: {pr['study']['question']}  ",
        f"Pre-registered {pr['study']['registered']} (config/experiments/preregistration.toml). "
        f"Cases: {pr['study']['cases']}; experiments on {', '.join(pr['study']['dev_splits'])} "
        f"(n={len(split_cases('dev'))}). Primary metric: success within "
        f"{timeout_ms() / 1000:.0f} s. Headline: {pr['metric']['headline']}.",
        "",
        "All numbers come from offline replay of synthetic-authored model behaviour.",
        "",
    ]
    for e in log_entries():
        v = X.variants()[e["variant"]]
        a, b = summary(v.parent), summary(v.name)
        p = paired(v.parent, v.name)
        dec, why = verdict(e)
        lines += [
            f"## {e['id']}: {v.label} vs {X.variants()[v.parent].label} ({e['date']})",
            "",
            f"- **Change (one):** {v.change}",
            f"- **Hypothesis:** {e['hypothesis']}",
            f"- **Expected:** {e['expected']}",
            f"- **Decision rule:** {e['kind']}"
            + (f" (margin {margin():.2f})" if e["kind"] == "non-inferiority" else ""),
            f"- **Result:** success {a.rate:.3f} -> {b.rate:.3f}, paired diff {p.diff:+.3f} "
            f"[{p.low:+.3f}, {p.high:+.3f}] (only parent {p.a_only}, only variant {p.b_only}); "
            f"cost/success {money(a.cost_per_success)} -> {money(b.cost_per_success)}; "
            f"p95 {a.p95_ms / 1000:.2f} -> {b.p95_ms / 1000:.2f} s",
            f"- **Decision:** {dec} ({why})",
            "",
        ]
    return "\n".join(lines)


def weakest_step(d: Decision) -> str:
    """The kept accuracy change with the fewest tasks behind it, and its exact McNemar p-value."""
    kinds = {e["variant"]: e["kind"] for e in log_entries()}
    steps = [(n, paired(X.variants()[n].parent, n)) for n in d.kept[1:] if kinds[n] != "no-change"]
    steps = [(n, p) for n, p in steps if p.a_only + p.b_only > 0]
    if not steps:
        return "- No kept change moved any task's outcome."
    n, p = min(steps, key=lambda np_: np_[1].a_only + np_[1].b_only)
    return (
        f"- The thinnest step is {X.variants()[n].label}: it rests on {p.a_only + p.b_only} tasks "
        f"that changed outcome ({p.b_only} fixed, {p.a_only} broken; exact McNemar "
        f"p={p.p_value:.2f}). Read it as likely, not proven."
    )


def memo_markdown(today: str | None = None) -> str:
    """A one-page decision memo, drafted from the numbers. Edit before sending: it is a draft."""
    d = decide()
    vs = X.variants()
    s = {n: summary(n) for n in vs}
    rel = "v1"
    c, r = s[d.chosen], s[rel]
    dev_n = len(split_cases("dev"))
    pc = paired(rel, d.chosen)
    today = today or datetime.now().astimezone().date().isoformat()
    lines = [
        "# Decision memo: MediaDoctor release configuration",
        "",
        f"Date: {today} · Author: (you) · Status: draft for review",
        "",
        "## Decision requested",
        "",
        f"Switch MediaDoctor from **{vs[rel].label}** to **{vs[d.chosen].label}** "
        f"({vs[d.chosen].model}, prompt {vs[d.chosen].prompt}"
        + (", prompt caching" if vs[d.chosen].cache else "")
        + ").",
        "",
        "## Recommendation and why",
        "",
        f"- Task success on the dev set: **{r.rate:.0%} → {c.rate:.0%}** (paired difference "
        f"{pc.diff:+.1%}, 95% CI {pc.low:+.1%} to {pc.high:+.1%}, n={dev_n}).",
        f"- Cost per successful task: **{money(r.cost_per_success)} → "
        f"{money(c.cost_per_success)}** ({c.cost_per_success / r.cost_per_success - 1:+.0%}).",
        f"- Latency: p50 {r.p50_ms / 1000:.1f} s → {c.p50_ms / 1000:.1f} s; p95 "
        f"{r.p95_ms / 1000:.1f} s → {c.p95_ms / 1000:.1f} s.",
        f"- How we got there: {' → '.join(vs[n].label for n in d.kept)}, one change at a time, "
        "each kept only when it passed the rule written down before it ran.",
    ]
    if d.best != d.chosen:
        b = s[d.best]
        pb = paired(d.chosen, d.best)
        lines.append(
            f"- **{vs[d.best].label}** scored higher ({b.rate:.0%}, {pb.diff:+.1%}, CI "
            f"{pb.low:+.1%} to {pb.high:+.1%}) but did not pass its own rule: "
            f"{d.verdicts[d.best][1]}. It costs {b.cost_per_success / c.cost_per_success - 1:+.0%} "
            "per success. Not recommended on this evidence."
        )
    lines += [
        "",
        "## Options considered",
        "",
        "| Option | Success (95% CI) | Cost / success | p95 | Outcome |",
        "|---|---|---|---|---|",
    ]
    for n in vs:
        x = s[n]
        if n == d.chosen:
            status = "**recommended**"
        elif n == rel:
            status = "current release"
        elif n in d.kept:
            status = "kept; superseded by a later change"
        else:
            status = "rejected: " + d.verdicts[n][1]
        lines.append(
            f"| {vs[n].label} | {x.rate:.0%} ({x.low:.0%}–{x.high:.0%}) | "
            f"{money(x.cost_per_success)} | {x.p95_ms / 1000:.1f} s | {status} |"
        )
    disc = max((pc.a_only + pc.b_only) / pc.n, 0.05)
    lines += [
        "",
        "## How sure we are",
        "",
        f"- {dev_n} dev tasks, one run each. For two configurations that disagree on {disc:.0%} of "
        f"tasks (as {rel} and the recommendation do), this many tasks reliably detects a difference "
        f"of about {mdd_paired(dev_n, disc):.0%} (80% power); smaller ones can hide in the noise.",
        weakest_step(d),
        f"- The held-out split ({len(split_cases('holdout'))} tasks) is untouched; it is read once, "
        "for the recommended option, before release. Its interval will be wide.",
        "- Success is scored by code checks and a reference check of the diagnosis, not by users.",
        "- Costs are list prices from config/models.toml and assume steady traffic keeps the "
        "prompt cache warm (it expires after 5 minutes unused).",
        "",
        "## What we are not saying",
        "",
        f'- Not "{c.rate:.0%} accurate in production": production questions differ from the dev set.',
        '- Not "Haiku is worse" in general: it is worse for this agent, prompt, and task mix.',
        "- Not that the rejected options are dead: each rejection names what would change it.",
        "",
        "## Next steps",
        "",
        f"1. Run `mediadoctor-lab11 confirm {d.chosen} --release` once and attach the result.",
        "2. If it holds, change config/release.toml and track cost per successful task in production.",
        "3. Re-open the question when prices, models, traffic, or the failure taxonomy change.",
    ]
    return "\n".join(lines) + "\n"


# --- 6. The held-out confirmation -----------------------------------------------------------------------


def confirm_holdout(variant: str, release: bool, guard: HoldoutGuard | None = None,
                    log_path: Path | None = None) -> tuple[Summary, Summary, PairedResult]:  # fmt: skip
    """Run `variant` and the release configuration on the held-out split, once, and log the look."""
    guard = guard or holdout_guard()
    cases = split_cases("holdout")
    guard.check([c["id"] for c in cases], f"confirm {variant}", release=release)
    rel = "v1"
    rows = {n: [to_row(X.run_task(c, n)) for c in cases] for n in (rel, variant)}
    sa, sb = summarize(rel, rows[rel]), summarize(variant, rows[variant])
    p = paired_bootstrap_diff(
        [r.success for r in rows[rel]], [r.success for r in rows[variant]], seed=11
    )  # noqa: E501
    log_path = log_path or RUNS / "holdout_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["when", "variant", "n", "success", "release_success"])
        w.writerow([datetime.now().astimezone().isoformat(timespec="seconds"), variant, len(cases),
                    f"{sb.rate:.3f}", f"{sa.rate:.3f}"])  # fmt: skip
    return sa, sb, p


# --- CLI ------------------------------------------------------------------------------------------------


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mediadoctor-lab11", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    names = list(X.variants())
    sub.add_parser("ev")
    sub.add_parser("variants")
    sp = sub.add_parser("run")
    sp.add_argument("variant", choices=names)
    sp = sub.add_parser("report")
    sp.add_argument("--only", nargs="+", choices=names)
    sp.add_argument("--out")
    sp = sub.add_parser("pareto")
    sp.add_argument("--svg")
    sp = sub.add_parser("latency")
    sp.add_argument("variant", choices=names)
    sp.add_argument("--vs", choices=names)
    sp = sub.add_parser("trace")
    sp.add_argument("variant", choices=names)
    sp.add_argument("case")
    sp = sub.add_parser("cost")
    sp.add_argument("--runs", type=int, default=1)
    sp = sub.add_parser("log")
    sp.add_argument("--out")
    sp = sub.add_parser("memo")
    sp.add_argument("--out")
    sp = sub.add_parser("confirm")
    sp.add_argument("variant", choices=names)
    sp.add_argument("--release", action="store_true", help="this is the one pre-release look")
    a = ap.parse_args(argv)

    if a.cmd == "ev":
        print(ev_text())
    elif a.cmd == "variants":
        for v in X.variants().values():
            print(f"{v.name:9s} parent {v.parent or '-':9s} {v.model:18s} prompt {v.prompt} "
                  f"cache {'on ' if v.cache else 'off'} {v.strategy:8s} | {v.change}")  # fmt: skip
    elif a.cmd == "run":
        print(f"{'case':7s} {'ok':3s} {'checks failed':28s} {'latency':>8s} {'cost':>9s} calls")
        for r in run_rows(a.variant):
            failed = [k for k, ok in r.checks if not ok] + (["timeout"] if r.timed_out else [])
            print(f"{r.case_id:7s} {'yes' if r.success else 'NO ':3s} {','.join(failed) or '-':28s} "
                  f"{r.latency_ms / 1000:7.2f}s {money(r.cost_usd):>9s} {r.calls}")  # fmt: skip
        s = summary(a.variant)
        print(f"\nsuccess {s.successes}/{s.n} = {s.rate:.3f} [{s.low:.3f}, {s.high:.3f}]  "
              f"cost/success {money(s.cost_per_success)}")  # fmt: skip
    elif a.cmd == "report":
        _write(report_text(a.only), a.out)
    elif a.cmd == "pareto":
        front = pareto_front([summary(n) for n in names])
        print(
            "frontier: "
            + " -> ".join(f"{p.variant} ({money(p.cost_per_task)}, {p.rate:.3f})" for p in front)
        )  # noqa: E501
        best = cheapest_within([summary(n) for n in names])
        print(f"cheapest within 2 points of the best (point estimates): {best.variant}")
        if a.svg:
            _write(pareto_svg(), a.svg)
    elif a.cmd == "latency":
        print(latency_text(a.variant, a.vs))
    elif a.cmd == "trace":
        print(trace_text(a.variant, a.case))
    elif a.cmd == "cost":
        print(cost_text(a.runs))
    elif a.cmd == "log":
        _write(log_markdown(), a.out)
    elif a.cmd == "memo":
        _write(memo_markdown(), a.out)
    elif a.cmd == "confirm":
        try:
            sa, sb, p = confirm_holdout(a.variant, a.release)
        except HoldoutAccessError as exc:
            print(f"refused: {exc}\n(add --release for the one pre-release look; it is logged)")
            return 2
        print(f"held-out (n={sb.n}): v1 {sa.rate:.3f}  {a.variant} {sb.rate:.3f} "
              f"[{sb.low:.3f}, {sb.high:.3f}]  paired diff {p.diff:+.3f} [{p.low:+.3f}, {p.high:+.3f}]")  # fmt: skip
        print(f"cost/success {money(sa.cost_per_success)} -> {money(sb.cost_per_success)}; "
              f"look logged in {RUNS / 'holdout_log.csv'}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
