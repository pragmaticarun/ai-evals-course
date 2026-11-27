"""Module 6 lab: metrics you can trust for MediaDoctor.

    uv run mediadoctor-lab06 runs                  # every recorded run, pass rate with a Wilson CI
    uv run mediadoctor-lab06 variance              # 5 repeated runs on the dev queries
    uv run mediadoctor-lab06 show m4q021           # one query's answers across every run
    uv run mediadoctor-lab06 compare               # prompt v1 vs v2 on the same 137 queries
    uv run mediadoctor-lab06 modes                 # per-failure-mode table, paired tests, Holm
    uv run mediadoctor-lab06 slices                # v1 vs v2 by topic, and why slicing misleads
    uv run mediadoctor-lab06 samples               # how many queries a decision needs
    uv run mediadoctor-lab06 vanity                # a 1-10 helpfulness score and text similarity
    uv run mediadoctor-lab06 judges                # module 5's judge numbers with honest error bars
    uv run mediadoctor-lab06 report --out report.md

Replay mode (default) needs no API key. Run 1 of prompt v1 is the module 5 run; the other runs, the
outcome labels, the reference answers, and the helpfulness scores are synthetic-authored (see
scripts/author_module06_fixtures.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import LLM, Mode, Tracer, load_models, repo_root, text_of
from evalkit.judge import Item
from evalkit.stats import (
    PairedResult,
    bootstrap_ci,
    holm,
    mdd_paired,
    mdd_two_proportions,
    n_for_halfwidth,
    n_paired,
    n_two_proportions,
    paired_bootstrap_diff,
    pass_at_k,
    pass_hat_k,
    trial_summary,
    wilson_interval,
)
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from mediadoctor import lab03, lab05
from mediadoctor.toolagent import run_agent

AGENT_NAMESPACE = "mediadoctor-m6"
JUDGE_NAMESPACE = "mediadoctor-m6-judges"
PROMPTS = ("v1", "v2")
RUNS = 5  # repeated runs on the dev queries; run 1 covers all 137 queries
DRAWS = 2000
SEED = 6
MODES = (
    "accepted-false-premise",
    "ignored-tool-output",
    "vague-next-step",
    "assumed-unstated-detail",
    "format-violation",
    "skipped-investigation",
    "fabricated-evidence",
    "wrong-api-detail",
)

Trace = list[dict[str, Any]]
Key = tuple[str, int]  # (prompt version, run number from 1)


def labels_path() -> Path:
    return repo_root() / "data" / "labels" / "module06_runs.csv"


def references_path() -> Path:
    return repo_root() / "data" / "labels" / "module06_reference_answers.csv"


def all_ids() -> list[str]:
    return [r["id"] for r in lab05.label_rows()]


def repeat_ids() -> list[str]:
    """The queries every run covers: the 37 dev-split queries."""
    return lab05.ids_in("dev")


def run_keys() -> list[Key]:
    return [(p, r) for p in PROMPTS for r in range(1, RUNS + 1)]


def ids_for(run: int) -> list[str]:
    return all_ids() if run == 1 else repeat_ids()


# --- Replaying the runs -------------------------------------------------------------------------------


def agent_llm(run: int) -> LLM:
    """Run n replays trial n-1: the same requests, recorded again (a new sample from the model)."""
    return LLM(namespace=AGENT_NAMESPACE, trial=run - 1)


def run_traces(prompt: str, run: int, llm: LLM | None = None) -> dict[str, Trace]:
    if (prompt, run) == ("v1", 1):
        return lab05.traces()  # module 5's run of prompt v1 is run 1
    llm = llm or agent_llm(run)
    live = llm.mode is not Mode.REPLAY
    rows = {r["id"]: r for r in lab05.label_rows()}
    spans: list[dict[str, Any]] = []
    for i, cid in enumerate(ids_for(run)):
        tracer = (
            Tracer()
            if live
            else Tracer(
                clock=VirtualClock(VIRTUAL_EPOCH_NS + i * 60_000_000_000),
                ids=SeededIds(f"mediadoctor-lab06:{prompt}:{run}:{cid}"),
            )
        )
        run_agent(rows[cid]["question"], llm=llm, tracer=tracer, case_id=cid, prompt_version=prompt)
        spans.extend(tracer.span_dicts())
    return lab03.traces_by_case(spans)


@cache
def items(prompt: str, run: int) -> dict[str, Item]:
    return {cid: lab05.item_from_trace(t) for cid, t in run_traces(prompt, run).items()}


# --- Outcomes -----------------------------------------------------------------------------------------


@cache
def labels() -> dict[Key, dict[str, frozenset[str]]]:
    """{(prompt, run): {case_id: failure modes}} from the reference labels of every run."""
    out: dict[Key, dict[str, frozenset[str]]] = {}
    with labels_path().open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            modes = frozenset(m for m in r["modes"].split(";") if m)
            out.setdefault((r["prompt"], int(r["run"])), {})[r["case_id"]] = modes
    return out


def outcomes(
    prompt: str, run: int, mode: str | None = None, ids: Sequence[str] | None = None
) -> dict[str, bool]:
    """PASS per query: no failure at all, or (with `mode`) not that failure mode."""
    lab = labels()[(prompt, run)]
    ids = ids if ids is not None else list(lab)
    return {c: (not lab[c]) if mode is None else (mode not in lab[c]) for c in ids}


def paired(mode: str | None = None, ids: Sequence[str] | None = None, seed: int = SEED):
    a = outcomes("v1", 1, mode, ids)
    b = outcomes("v2", 1, mode, ids)
    keys = sorted(a)
    return paired_bootstrap_diff([a[k] for k in keys], [b[k] for k in keys], draws=DRAWS, seed=seed)


def repeated(prompt: str, mode: str | None = None) -> dict[str, list[bool]]:
    ids = repeat_ids()
    per_run = [outcomes(prompt, r, mode, ids) for r in range(1, RUNS + 1)]
    return {c: [o[c] for o in per_run] for c in ids}


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def fmt_ci(k: int, n: int) -> str:
    lo, hi = wilson_interval(k, n)
    return f"{k / n:.2f} [{lo:.2f}, {hi:.2f}]"


def mode_table(ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Per failure mode, run 1: failure rate of each prompt with a Wilson CI, and the paired
    difference with a bootstrap CI, exact McNemar p, and Holm-adjusted p across the modes."""
    rows = []
    for m in MODES:
        a = outcomes("v1", 1, m, ids)
        b = outcomes("v2", 1, m, ids)
        fa, fb = sum(not v for v in a.values()), sum(not v for v in b.values())
        if fa == fb == 0:
            continue
        res = paired(m, ids)
        rows.append({"mode": m, "n": res.n, "v1_fail": fa, "v2_fail": fb, "paired": res})
    adj = holm({r["mode"]: r["paired"].p_value for r in rows})
    for r in rows:
        r["holm"] = adj[r["mode"]]
    return rows


# --- Vanity metrics -----------------------------------------------------------------------------------

HELPFUL_SYSTEM = """\
You rate answers from MediaDoctor, an assistant for Android and multimedia engineers.
How helpful is this answer, on a scale from 1 (useless) to 10 (extremely helpful)?
Respond with JSON only: {"reason": "<one sentence>", "score": <1-10>}"""


def helpfulness_request(item: Item) -> dict[str, Any]:
    role = load_models()["judge"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": HELPFUL_SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": f"<question>\n{item.question}\n</question>\n<answer>\n{item.answer}\n</answer>",
            }
        ],
    }


def helpfulness(prompt: str, llm: LLM | None = None) -> dict[str, int]:
    """A generic 1-10 'helpfulness' judge on run 1 of a prompt (replayed)."""
    llm = llm or LLM(namespace=JUDGE_NAMESPACE)
    out = {}
    for cid, item in items(prompt, 1).items():
        text = text_of(llm.create(**helpfulness_request(item)))
        out[cid] = int(json.loads(re.search(r"\{.*\}", text, re.S).group(0))["score"])
    return out


@cache
def reference_answers() -> dict[str, str]:
    with references_path().open(newline="", encoding="utf-8") as fh:
        return {r["case_id"]: r["reference"] for r in csv.DictReader(fh)}


_WORD = re.compile(r"[a-z0-9]+")


def token_f1(candidate: str, reference: str) -> float:
    """Word-overlap F1, the kind of off-the-shelf similarity used in QA benchmarks."""
    c, r = Counter(_WORD.findall(candidate.lower())), Counter(_WORD.findall(reference.lower()))
    common = sum((c & r).values())
    if not common:
        return 0.0
    precision, recall = common / sum(c.values()), common / sum(r.values())
    return 2 * precision * recall / (precision + recall)


def similarity(prompt: str = "v1") -> dict[str, float]:
    refs = reference_answers()
    return {cid: token_f1(it.answer, refs[cid]) for cid, it in items(prompt, 1).items()}


def separation(scores: dict[str, float], passed: dict[str, bool]) -> float:
    """Chance that a random passing answer scores higher than a random failing one (AUC; ties
    count half). 0.5 means the score cannot tell them apart."""
    pos = [scores[c] for c in scores if passed[c]]
    neg = [scores[c] for c in scores if not passed[c]]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


# --- Sample sizes -------------------------------------------------------------------------------------


def discordant_share() -> float:
    res = paired()
    return (res.a_only + res.b_only) / res.n


# --- Report -------------------------------------------------------------------------------------------


def _diff(res: PairedResult, sign: int = 1) -> str:
    d, lo, hi = sign * res.diff, sign * res.low, sign * res.high
    lo, hi = min(lo, hi), max(lo, hi)
    return f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]"


def report() -> str:
    """The metric dashboard, as Markdown."""
    n = len(all_ids())
    a, b = outcomes("v1", 1), outcomes("v2", 1)
    res = paired()
    lines = [
        "# MediaDoctor metric report: agent prompt v1 vs v2",
        "",
        f"Run 1 of each prompt on the same {n} labelled queries. Rates with 95% Wilson intervals;",
        f"differences are v2 minus v1 with 95% paired bootstrap intervals ({DRAWS} draws) and exact",
        "McNemar p-values, Holm-adjusted across failure modes. Labels: reference (synthetic-authored).",
        "",
        "## Overall",
        "",
        "| Metric | v1 | v2 | v2 - v1 | McNemar p |",
        "|---|---|---|---|---|",
        f"| Pass rate (no failure mode) | {fmt_ci(sum(a.values()), n)} | {fmt_ci(sum(b.values()), n)} "
        f"| {_diff(res)} | {fmt_p(res.p_value)} |",
        "",
        "## Per failure mode (failure rate, lower is better)",
        "",
        "| Failure mode | v1 | v2 | v2 - v1 | p | Holm p |",
        "|---|---|---|---|---|---|",
    ]
    for r in mode_table():
        h = fmt_p(r["holm"])
        lines.append(
            f"| {r['mode']} | {fmt_ci(r['v1_fail'], r['n'])} | {fmt_ci(r['v2_fail'], r['n'])} "
            f"| {_diff(r['paired'], -1)} | {fmt_p(r['paired'].p_value)} "
            f"| {f'**{h}**' if r['holm'] < 0.05 else h} |"
        )
    lines += [
        "",
        f"## Reliability: {RUNS} runs of each prompt on the {len(repeat_ids())} dev queries",
        "",
        "| Prompt | Mean pass rate | Run-to-run range | pass^5 | Flaky queries |",
        "|---|---|---|---|---|",
    ]
    for p in PROMPTS:
        rep = repeated(p)
        s = trial_summary(rep)
        hat = sum(pass_hat_k(RUNS, sum(v), RUNS) for v in rep.values()) / len(rep)
        lines.append(
            f"| {p} | {s.mean_rate:.2f} | {min(s.run_rates):.2f} to {max(s.run_rates):.2f} "
            f"| {hat:.2f} | {s.flaky} of {s.n_cases} |"
        )
    disc = discordant_share()
    lines += [
        "",
        "## What this data can detect",
        "",
        f"- With {n} paired queries and {disc:.0%} discordant pairs, the smallest overall change "
        f"detectable at 80% power is about {100 * mdd_paired(n, disc):.0f} points (paired), versus "
        f"{100 * mdd_two_proportions(n, sum(a.values()) / n):.0f} if v1 and v2 ran on different queries.",
        "- Bold Holm p: below 0.05 after adjusting for the number of failure modes tested.",
        "- Small counts: with fewer than about 10 discordant queries, trust the exact McNemar p over",
        "  the bootstrap interval, which is too narrow for very small counts.",
        "",
    ]
    return "\n".join(lines)


# --- CLI ----------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mediadoctor-lab06", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("runs", help="every recorded run with a Wilson interval")
    v = sub.add_parser("variance", help="repeated runs on the dev queries")
    v.add_argument("--mode", choices=MODES)
    sub.add_parser("show", help="one query's answers and labels across every run").add_argument(
        "case_id"
    )
    c = sub.add_parser("compare", help="prompt v1 vs v2 on the same queries")
    c.add_argument("--mode", choices=MODES)
    sub.add_parser("modes", help="per-failure-mode table with paired tests")
    sub.add_parser("slices", help="v1 vs v2 by topic")
    sub.add_parser("samples", help="sample sizes and detectable differences")
    sub.add_parser("vanity", help="helpfulness 1-10 and text similarity vs the labels")
    sub.add_parser("judges", help="module 5 judge numbers with Wilson intervals")
    r = sub.add_parser("report", help="the Markdown metric report")
    r.add_argument("--out")
    args = p.parse_args(argv)

    if args.cmd == "runs":
        for prompt, run in run_keys():
            o = outcomes(prompt, run)
            k = sum(o.values())
            print(f"{prompt} run {run}: {len(o):>3} queries, pass {k:>3}  {fmt_ci(k, len(o))}")
        return 0
    if args.cmd == "variance":
        for prompt in PROMPTS:
            rep = repeated(prompt, args.mode)
            s = trial_summary(rep)
            print(f"{prompt}: {s}")
            for k in (1, 3, 5):
                at = sum(pass_at_k(RUNS, sum(x), k) for x in rep.values()) / len(rep)
                hat = sum(pass_hat_k(RUNS, sum(x), k) for x in rep.values()) / len(rep)
                print(f"    k={k}: pass@k {at:.3f}  pass^k {hat:.3f}")
        return 0
    if args.cmd == "show":
        for prompt, run in run_keys():
            if args.case_id not in ids_for(run):
                continue
            modes = labels()[(prompt, run)][args.case_id]
            lines = items(prompt, run)[args.case_id].answer.splitlines()
            verdict = "FAIL " + ", ".join(sorted(modes)) if modes else "PASS"
            print(f"{prompt} run {run}: {verdict}")
            for ln in lines[:2]:
                print(f"    {ln[:150]}")
        return 0
    if args.cmd == "compare":
        a, b = outcomes("v1", 1, args.mode), outcomes("v2", 1, args.mode)
        n = len(a)
        print(f"v1: {fmt_ci(sum(a.values()), n)}   v2: {fmt_ci(sum(b.values()), n)}   (Wilson)")
        print(f"paired (v2 - v1): {paired(args.mode)}")
        return 0
    if args.cmd == "modes":
        print("| Failure mode | v1 fail | v2 fail | v2 - v1 | p | Holm p |")
        print("|---|---|---|---|---|---|")
        for row in mode_table():
            print(
                f"| {row['mode']} | {fmt_ci(row['v1_fail'], row['n'])} | {fmt_ci(row['v2_fail'], row['n'])} "
                f"| {_diff(row['paired'], -1)} | {fmt_p(row['paired'].p_value)} | {fmt_p(row['holm'])} |"
            )
        return 0
    if args.cmd == "slices":
        rows = lab05.label_rows()
        topics = sorted({x["topic"] for x in rows})
        res = {t: paired(None, [x["id"] for x in rows if x["topic"] == t]) for t in topics}
        adj = holm({t: x.p_value for t, x in res.items()})
        for t in topics:
            x = res[t]
            print(
                f"{t:<15} n={x.n:>2}  v1 {x.rate_a:.2f}  v2 {x.rate_b:.2f}  "
                f"diff {x.diff:+.2f} [{x.low:+.2f}, {x.high:+.2f}]  p={x.p_value:.3f}  Holm p={adj[t]:.3f}"
            )
        return 0
    if args.cmd == "samples":
        n = len(all_ids())
        p1 = sum(outcomes("v1", 1).values()) / n
        disc = discordant_share()
        print(f"v1 pass rate {p1:.2f} on {n} queries; v1/v2 discordant share {disc:.2f}")
        print(f"queries for a +/-5-point interval on one rate: {n_for_halfwidth(p1, 0.05)}")
        p2 = p1 + 0.05 if p1 + 0.05 <= 1 else p1 - 0.05  # a 5-point change that fits in [0, 1]
        print(
            f"to detect {p1:.2f} -> {p2:.2f} (80% power, alpha 0.05): "
            f"{n_two_proportions(p1, p2)} per prompt on separate queries, "
            + (
                f"{n_paired(disc, 0.05)} shared queries if paired"
                if disc > 0.05
                else f"and pairing cannot detect it: the prompts disagree on only {disc:.0%} of queries"
            )
        )
        print(
            f"smallest detectable change with {n} queries: {mdd_two_proportions(n, p1):.3f} unpaired, "
            f"{mdd_paired(n, disc):.3f} paired"
        )
        return 0
    if args.cmd == "vanity":
        for prompt in PROMPTS:
            h = helpfulness(prompt)
            ok = outcomes(prompt, 1)
            mean_all, lo, hi = bootstrap_ci(
                list(h.values()), lambda xs: sum(xs) / len(xs), DRAWS, SEED
            )
            mp = sum(h[c] for c in h if ok[c]) / sum(ok.values())
            mf = sum(h[c] for c in h if not ok[c]) / sum(not v for v in ok.values())
            print(
                f"{prompt} helpfulness: mean {mean_all:.2f} [{lo:.2f}, {hi:.2f}]; "
                f"passing answers {mp:.2f}, failing answers {mf:.2f}; "
                f"separation (AUC) {separation({c: float(x) for c, x in h.items()}, ok):.2f}"
            )
        sim, ok = similarity("v1"), outcomes("v1", 1)
        mp = sum(sim[c] for c in sim if ok[c]) / sum(ok.values())
        mf = sum(sim[c] for c in sim if not ok[c]) / sum(not v for v in ok.values())
        print(
            f"v1 token F1 vs reference answer: passing {mp:.2f}, failing {mf:.2f}; "
            f"separation (AUC) {separation(sim, ok):.2f}"
        )
        return 0
    if args.cmd == "judges":
        for split in ("dev", "test"):
            for name in lab05.FINAL:
                res = lab05.validate(name, None, split).result
                pos, neg = res.tp + res.fn, res.tn + res.fp
                print(
                    f"{name:<15} {split:<4}  TPR {fmt_ci(res.tp, pos)} (n={pos:>2})  "
                    f"TNR {fmt_ci(res.tn, neg)} (n={neg})"
                )
        est, truth, _ = lab05.estimate()
        print(f"tool-grounding corrected estimate: {est}; reference {truth:.3f}")
        return 0
    if args.cmd == "report":
        text = report()
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
