"""Module 12 capstone: run the whole eval loop offline and write the eval report.

    uv run mediadoctor-capstone run                       # every stage, modules 1 to 11, one line each
    uv run mediadoctor-capstone slices                    # baseline vs candidate per topic: choose a slice
    uv run mediadoctor-capstone report [--slice TOPIC] [--release] [--date YYYY-MM-DD] [--out FILE]
    uv run mediadoctor-capstone check FILE                # self-review: does a report follow the template?

Everything replays from the fixtures the earlier modules recorded and needs no API key. The model behaviour in
those fixtures is synthetic-authored (see each module's lab); the agent loop, tools, checks, judges' prompts,
prices, and statistics are real code. `--release` spends the one look at the held-out split and logs it in
runs/capstone/holdout_log.csv; leave it off while you iterate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import repo_root
from evalkit.golden import load_manifest
from evalkit.stats import (
    PairedResult,
    mdd_paired,
    n_paired,
    paired_bootstrap_diff,
    percentile,
    trial_summary,
    wilson_interval,
)
from mediadoctor import experiments as X

BASELINE = "v1"  # what config/release.toml ships today
DEFAULT_SLICE = None  # None: the topic where the candidate does worst on dev
MODE_NAMES = {  # module 11's label codes -> the taxonomy's mode ids (modules 3 and 4)
    "premise": "accepted-false-premise",
    "ignored": "ignored-tool-output",
    "skipped": "skipped-investigation",
    "format": "format-violation",
}
SECTIONS = (
    "Decision requested",
    "Summary",
    "Scope",
    "Data",
    "Failure taxonomy",
    "Evaluators",
    "Results",
    "Risks and caveats",
    "Recommendation and next steps",
    "Appendix",
)
HOLDOUT_LOG = Path("runs") / "capstone" / "holdout_log.csv"


# --- formatting -------------------------------------------------------------------------------------------


def r3(x: float) -> str:
    return f"{x:.3f}"


def ci(lo: float, hi: float, signed: bool = False) -> str:
    f = "{:+.3f}" if signed else "{:.3f}"
    return "[" + f.format(lo) + ", " + f.format(hi) + "]"


def rate(k: int, n: int) -> str:
    """'0.667 (72/108) [0.573, 0.748]': a rate, its counts, and its Wilson 95% interval."""
    if n == 0:
        return "n/a (0 cases)"
    lo, hi = wilson_interval(k, n)
    return f"{k / n:.3f} ({k}/{n}) {ci(lo, hi)}"


def diff(p: PairedResult) -> str:
    return f"{p.diff:+.3f} {ci(p.low, p.high, signed=True)}"


def money(x: float) -> str:
    return f"${x:.5f}"


def table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def mods(n: int) -> str:
    """Relative link from docs/capstone/ to a module's lesson."""
    return f"../modules/{MODULE_DIRS[n]}/index.md"


MODULE_DIRS = {
    1: "01-why-evals",
    2: "02-agent-with-tracing",
    3: "03-error-analysis",
    4: "04-synthetic-data",
    5: "05-evaluators-and-judges",
    6: "06-trustworthy-metrics",
    7: "07-architectures",
    8: "08-ci-cd",
    9: "09-monitoring-and-annotation",
    10: "10-red-teaming",
    11: "11-improving-with-evidence",
    12: "12-capstone",
}


# --- the stages -------------------------------------------------------------------------------------------
# Each stage replays one module's artifacts and returns plain numbers. Import lazily so `--help` is fast.


@dataclass(frozen=True)
class Stage:
    module: int
    name: str
    headline: str
    ok: bool = True  # False: the stage found something the report must flag


@cache
def m01() -> dict[str, Any]:
    from mediadoctor import lab01

    s1, s2 = lab01.evaluate("v1")["summary"], lab01.evaluate("v2")["summary"]
    return {"v1": s1, "v2": s2}


@cache
def m02() -> dict[str, Any]:
    from mediadoctor import lab02

    spans = lab02.run_cases()
    res = lab02.check_traces(spans)
    names = list(next(iter(res.values())))
    per_check = {c: (sum(r[c] for r in res.values()), len(res)) for c in names}
    return {"n_traces": len(res), "n_spans": len(spans), "checks": per_check}


@cache
def m03() -> dict[str, Any]:
    from mediadoctor import lab03

    anns = lab03.load_annotations(lab03.reference_labels_path())
    modes = lab03.load_modes(lab03.reference_modes_path())
    ranked = lab03.rank_modes(anns, modes)
    upstream = Counter(a.first_upstream for a in anns if a.verdict == "fail" and a.first_upstream)
    return {
        "n": len(anns),
        "failing": sum(a.verdict == "fail" for a in anns),
        "ranked": ranked,
        "upstream": upstream,
        "examples": {r.mode.id: r.examples[:1] for r in ranked},
    }


@cache
def m04() -> dict[str, Any]:
    from mediadoctor import lab04

    space = lab04.load_default_space()
    ds = lab04.load_dataset()
    splits = Counter(r["split"] for r in ds)
    cov = {s: lab04.pair_coverage([r for r in ds if r["split"] == s], space) for s in splits}
    return {"n": len(ds), "splits": splits, "coverage": cov, "all": lab04.pair_coverage(ds, space),
            "dims": space.names}  # fmt: skip


@cache
def m05() -> dict[str, Any]:
    from mediadoctor import lab05

    judges = {name: lab05.validate(name, None, "test") for name in lab05.FINAL}
    est, truth, _ = lab05.estimate()
    return {"judges": judges, "versions": dict(lab05.FINAL), "estimate": est, "truth": truth}


@cache
def m06() -> dict[str, Any]:
    from mediadoctor import lab06

    rep = lab06.repeated("v2")
    s = trial_summary(rep)
    return {"paired": lab06.paired(), "trials": s, "flaky": s.n_cases - s.always_pass - s.never_pass,
            "disc": lab06.discordant_share()}  # fmt: skip


@cache
def m07() -> dict[str, Any]:
    from mediadoctor import lab07

    rows = {r["config"]: r for r in lab07.retrieval_rows()}
    (d, lo, hi), n = lab07.recall_diff(("fixed", "keyword"), ("section", "bm25"))
    runs = lab07.rag_runs()
    by_sys: dict[str, dict[str, bool]] = {}
    for rid in runs:
        system, qid = rid.split(":", 1)
        by_sys.setdefault(system, {})[qid] = lab07.rag_pass(rid)
    ids = sorted(by_sys["baseline"])
    rag_p = paired_bootstrap_diff([by_sys["baseline"][i] for i in ids], [by_sys["improved"][i] for i in ids],
                                  seed=7)  # fmt: skip
    return {
        "retrieval": rows,
        "recall_diff": (d, lo, hi, n),
        "rag_paired": rag_p,
        "attribution": lab07.attribution("improved"),
        "faithfulness": lab07.rag_judge_confusion("faithfulness"),
        "relevance": lab07.rag_judge_confusion("answer-relevance"),
    }


@cache
def m08() -> dict[str, Any]:
    from mediadoctor import lab08

    base = lab08.load_baseline().run
    head = lab08.run_suite(None, ("code", "judges"))
    gates = {t: lab08.compare(base, head, t) for t in ("code", "judges")}
    m = load_manifest(lab08.manifest_path())
    return {
        "status": lab08.overall(gates).value,
        "tiers": {t: g.status.value for t, g in gates.items()},
        "manifest": f"{m['name']} {m['version']}",
        "manifest_problems": lab08.manifest_problems(),
        "n_files": len(m["files"]),
        "splits": {k: len(v) for k, v in m["splits"].items()},
    }


@cache
def m09() -> dict[str, Any]:
    from mediadoctor import lab09

    alarms = {
        m: lab09.cusum_alarm(m)
        for m in ("evidence_fail", "tool_error", "thumbs_down", "format_fail")
    }
    return {
        "n": len(lab09.traffic()),
        "days": lab09.daily(),
        "alarms": alarms,
        "segments": lab09.segments("evidence_fail"),
        "tool_segments": lab09.segments("tool_error"),
        "rollout": lab09.ROLLOUT,
        "estimates": lab09.judge_estimates(),
    }


@cache
def m10() -> dict[str, Any]:
    from mediadoctor import lab10

    guards = ("none", "v1", "v2")
    return {
        "asr": {g: lab10.asr(g) for g in guards},
        "fpr": {g: lab10.fpr(g) for g in guards},
        "vectors": lab10.breakdown("vector"),
        "detector": lab10.detector_check(),
    }


@cache
def m11() -> dict[str, Any]:
    from mediadoctor import lab11

    d = lab11.decide()
    names = list(X.variants())
    return {
        "decision": d,
        "summaries": {n: lab11.summary(n) for n in names},
        "chain": [
            (d.kept[i - 1], d.kept[i], lab11.paired(d.kept[i - 1], d.kept[i]))
            for i in range(1, len(d.kept))
        ],
        "overall": lab11.paired(BASELINE, d.chosen),
        "selfcheck": lab11.selfcheck_stats(),
        "modes": {n: lab11.mode_counts(n) for n in (BASELINE, d.chosen)},
    }


def candidate() -> str:
    return m11()["decision"].chosen


# --- per-case data for the slice and the per-case diff ----------------------------------------------------


@cache
def dev_rows(variant: str) -> dict[str, Any]:
    from mediadoctor import lab11

    return {r.case_id: r for r in lab11.run_rows(variant)}


@cache
def case_by_id() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in X.cases()}


def labels() -> dict[tuple[str, str], str]:
    from mediadoctor import lab11

    return lab11.reference_labels()


def dev_ids(topic: str | None = None) -> list[str]:
    from mediadoctor import lab11

    return [c["id"] for c in lab11.split_cases("dev") if topic is None or c["topic"] == topic]


def paired_on(ids: Sequence[str], a: str, b: str) -> PairedResult:
    ra, rb = dev_rows(a), dev_rows(b)
    return paired_bootstrap_diff(
        [ra[i].success for i in ids], [rb[i].success for i in ids], seed=11
    )


def slice_rows() -> list[dict[str, Any]]:
    """Every topic: dev n, baseline and candidate success, and the paired difference."""
    cand = candidate()
    out = []
    for topic in sorted({c["topic"] for c in X.cases()}):
        ids = dev_ids(topic)
        a = sum(dev_rows(BASELINE)[i].success for i in ids)
        b = sum(dev_rows(cand)[i].success for i in ids)
        out.append(
            {
                "topic": topic,
                "n": len(ids),
                "base": a,
                "cand": b,
                "paired": paired_on(ids, BASELINE, cand),
            }
        )
    return out


def weakest_slice() -> str:
    rows = slice_rows()
    return min(rows, key=lambda r: (r["cand"] / r["n"], r["topic"]))["topic"]


def topics() -> list[str]:
    return sorted({c["topic"] for c in X.cases()})


@dataclass(frozen=True)
class Holdout:
    n: int
    base: int
    cand: int
    paired: PairedResult
    slice_n: int
    slice_base: int
    slice_cand: int


def holdout_look(topic: str, log_path: Path | None = None) -> Holdout:
    """The one release look at the held-out split, through module 8's guard, logged."""
    from mediadoctor import lab11

    cases = lab11.split_cases("holdout")
    guard = lab11.holdout_guard()
    guard.check([c["id"] for c in cases], f"capstone report: confirm {candidate()}", release=True)
    rows = {
        v: {c["id"]: lab11.to_row(X.run_task(c, v)) for c in cases} for v in (BASELINE, candidate())
    }
    ids = [c["id"] for c in cases]
    a = [rows[BASELINE][i].success for i in ids]
    b = [rows[candidate()][i].success for i in ids]
    sl = [c["id"] for c in cases if c["topic"] == topic]
    path = log_path or repo_root() / HOLDOUT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["when", "purpose", "variant", "n", "success", "baseline_success"])
        w.writerow([datetime.now().astimezone().isoformat(timespec="seconds"), "capstone report", candidate(),
                    len(ids), f"{sum(b) / len(b):.3f}", f"{sum(a) / len(a):.3f}"])  # fmt: skip
    return Holdout(len(ids), sum(a), sum(b), paired_bootstrap_diff(a, b, seed=11), len(sl),
                   sum(rows[BASELINE][i].success for i in sl), sum(rows[candidate()][i].success for i in sl))  # fmt: skip


@cache
def inputs_fingerprint() -> str:
    """sha256 over every recorded fixture, label file, and config file the stages read."""
    root = repo_root()
    h = hashlib.sha256()
    for sub in ("fixtures/recorded", "data", "config"):
        for p in sorted((root / sub).rglob("*")):
            if p.is_file():
                h.update(p.relative_to(root).as_posix().encode())
                h.update(p.read_bytes())
    return h.hexdigest()[:16]


# --- the pipeline -----------------------------------------------------------------------------------------


def stages() -> list[Stage]:
    s1, s2, s3, s4, s5, s6 = m01(), m02(), m03(), m04(), m05(), m06()
    s7, s8, s9, s10, s11 = m07(), m08(), m09(), m10(), m11()
    v1 = s1["v1"]["all_pass"]
    weakest = min(s2["checks"].items(), key=lambda kv: kv[1][0])
    top = s3["ranked"][0]
    tg = s5["judges"]["tool-grounding"].result
    best = max(s7["retrieval"].values(), key=lambda r: r["recall"][0])
    ef = s9["alarms"]["evidence_fail"]
    d = s11["decision"]
    cs = s11["summaries"][d.chosen]
    return [
        Stage(1, "baseline", f"v1 passes all three checks on {v1[0]}/{v1[1]} queries"),
        Stage(
            2,
            "tracing",
            f"{s2['n_traces']} traces, {s2['n_spans']} spans; weakest trace check "
            f"{weakest[0]} {weakest[1][0]}/{weakest[1][1]}",
        ),  # fmt: skip
        Stage(
            3,
            "error analysis",
            f"{s3['failing']}/{s3['n']} traces fail; top mode {top.mode.id} ({top.count})",
        ),
        Stage(
            4,
            "synthetic data",
            f"{s4['n']} queries; value pairs covered {s4['all'][0]}/{s4['all'][1]}",
        ),
        Stage(5, "judges", f"tool-grounding TPR {tg.tpr:.2f} TNR {tg.tnr:.2f} on test (n={tg.n})"),
        Stage(
            6,
            "statistics",
            f"v1->v2 {diff(s6['paired'])}; {s6['flaky']}/{s6['trials'].n_cases} queries flaky",
        ),
        Stage(
            7, "architecture", f"best retrieval {best['config']} recall@5 {best['recall'][0]:.2f}"
        ),
        Stage(
            8,
            "CI gate",
            f"gate {s8['status']}; {s8['manifest']}, manifest problems "
            f"{len(s8['manifest_problems'])}",
            ok=s8["status"] == "pass",
        ),  # fmt: skip
        Stage(
            9,
            "monitoring",
            f"evidence_fail CUSUM alarm {ef.hours_after_rollout:+.1f} h after the rollout"
            if ef.when
            else "no alarms",
            ok=ef.when is None,
        ),  # fmt: skip
        Stage(
            10,
            "red team",
            f"ASR {s10['asr']['none'].p:.3f} -> {s10['asr']['v2'].p:.3f} with guardrails v2, "
            f"benign FPR {s10['fpr']['v2'].p:.3f}",
        ),  # fmt: skip
        Stage(
            11,
            "improvement",
            f"{d.chosen}: success {cs.rate:.3f}, cost/success {money(cs.cost_per_success)}",
        ),
    ]


def render_stages(rows: Sequence[Stage]) -> str:
    return "\n".join(
        f"{s.module:>2}  {s.name:<15} {'ok  ' if s.ok else 'FLAG'}  {s.headline}" for s in rows
    )


def render_slices() -> str:
    cand = candidate()
    lines = [
        f"dev success per topic, {BASELINE} -> {cand} (paired 95% CI; small n, read the intervals)",
        "",
    ]
    lines.append(f"{'topic':16} {'n':>3}  {BASELINE:>6}  {cand:>6}  diff [95% CI]")
    for r in slice_rows():
        lines.append(f"{r['topic']:16} {r['n']:>3}  {r['base'] / r['n']:6.3f}  {r['cand'] / r['n']:6.3f}  "
                     f"{diff(r['paired'])}")  # fmt: skip
    lines.append(f"\nweakest slice under {cand}: {weakest_slice()}")
    return "\n".join(lines)


# --- the report -------------------------------------------------------------------------------------------


def _answer_line(variant: str, cid: str) -> str:
    t = X.run_task(case_by_id()[cid], variant)
    line = next((ln.strip() for ln in t.answer.splitlines() if ln.strip()), "")
    line = line.replace("|", "/")
    return line[:110] + ("..." if len(line) > 110 else "")


def _slice_section(topic: str, ho: Holdout | None) -> tuple[list[str], dict[str, Any]]:
    from mediadoctor import lab11

    cand = candidate()
    ids = dev_ids(topic)
    labs = labels()
    names = list(X.variants())
    rows = []
    for v in names:
        k = sum(dev_rows(v)[i].success for i in ids)
        rows.append([f"`{v}`", rate(k, len(ids))])
    modes = {v: Counter(labs[(v, i)] for i in ids) for v in (BASELINE, cand)}
    still = [i for i in ids if not dev_rows(cand)[i].success]
    p = paired_on(ids, BASELINE, cand)
    disc = max((p.a_only + p.b_only) / len(ids), 0.2)
    mdd = mdd_paired(len(ids), disc)
    need = max(0, n_paired(disc, 0.10) - len(ids))
    sc = Counter()
    for t in lab11.task_results("retry"):
        if t.case_id in ids:
            if t.retried:
                sc["retried"] += 1
                sc["fixed"] += labs[("retry", t.case_id)] == "none"
            bad = labs[("v3-cache", t.case_id)] != "none"
            failed = t.attempts[0].self_check is False
            sc[("bad" if bad else "good", "fail" if failed else "pass")] += 1
    cov = {}
    for dim in ("evidence", "ambiguity", "expertise", "persona", "goal"):
        cov[dim] = Counter(case_by_id()[i][dim] for i in ids)
    top_mode = (modes[cand] - Counter({"none": 10**6})).most_common(1)
    info = {"ids": ids, "paired": p, "still": still, "modes": modes, "mdd": mdd, "need": need, "sc": sc,
            "top_mode": top_mode[0][0] if top_mode else None}  # fmt: skip

    out = [f"### The {topic} slice", ""]
    out.append(
        f"Chosen because it is the topic where `{cand}` does worst on dev "
        f"(`uv run mediadoctor-capstone slices`). Every number below is on the {len(ids)} dev queries in this "
        f"topic, so the intervals are wide: read them before the point estimates."
        if topic == weakest_slice()
        else f"Chosen by the author of this report as a fresh slice. Every number below is on the {len(ids)} dev "
        f"queries in this topic, so the intervals are wide: read them before the point estimates."
    )
    out += ["", "**Every configuration on the slice** (success, Wilson 95% CI):", ""]
    out.append(table(["Configuration", f"Success on {topic}"], rows))
    out += ["", f"**Paired, {BASELINE} → {cand} on the slice:** {diff(p)}; fixed {p.b_only}, broken {p.a_only}, "
                f"McNemar p = {p.p_value:.2f}.", ""]  # fmt: skip
    mrows = []
    for code in ("premise", "ignored", "skipped", "format"):
        mrows.append([MODE_NAMES[code], modes[BASELINE][code], modes[cand][code]])
    out.append(table(["Failure mode (reference labels)", BASELINE, cand], mrows))
    out += ["", f"**Queries `{cand}` still fails on this slice** ({len(still)}):", ""]
    if still:
        srows = [[f"`{i}`", MODE_NAMES.get(labs[(cand, i)], labs[(cand, i)]) if labs[(cand, i)] != "none"
                  else "timeout or check failure", case_by_id()[i]["question"][:80].replace("|", "/")]
                 for i in still]  # fmt: skip
        out.append(table(["Case", "Mode", "Question"], srows))
    else:
        out.append("None. With this few queries that is not proof the slice is solved: the upper end of the "
                   "failure rate's interval is still well above zero.")  # fmt: skip
    good = sc[("good", "pass")] + sc[("good", "fail")]
    bad = sc[("bad", "pass")] + sc[("bad", "fail")]
    tpr = f"{sc[('good', 'pass')]}/{good}" if good else "n/a (no good first answers)"
    tnr = f"{sc[('bad', 'fail')]}/{bad}" if bad else "n/a (no defective first answers)"
    if sc["retried"]:
        retry_note = (f"It triggered {sc['retried']} retries here and {sc['fixed']} of them ended correct "
                      f"(across all dev topics: {selfcheck_fixed()}). Too few retries to say whether the retry "
                      "works better or worse here; what the slice does show is which failures survive it.")  # fmt: skip
    else:
        retry_note = (
            "It triggered no retries on this slice, so the slice says nothing about the retry step."
        )
    out += ["", "**The retry step's self-check judge on this slice** (first answers, PASS is positive): "
            f"TPR {tpr}, TNR {tnr}. {retry_note}"]  # fmt: skip
    gaps = [f"{d}: " + ", ".join(f"{v} {k}" for v, k in sorted(c.items())) for d, c in cov.items()]
    out += ["", "**Coverage of the slice** (dev queries per value):", ""] + [f"- {g}" for g in gaps]
    if ho is not None:
        out += ["", f"**Held out:** {ho.slice_n} test queries in this topic; {BASELINE} "
                    f"{rate(ho.slice_base, ho.slice_n)}, {cand} {rate(ho.slice_cand, ho.slice_n)}."]  # fmt: skip
    out += [
        "",
        f"**What the slice can and cannot show.** With {len(ids)} paired queries and a discordant share of "
        f"{disc:.2f}, "
        + (
            f"the smallest difference this slice can reliably detect is about {mdd:.2f} "
            if mdd == mdd
            else "no difference smaller than the discordant share itself can be reliably detected "
        )
        + f"(80% power, α = 0.05). A 10-point slice-specific improvement would need about {need} more queries "
        "in this topic, so the next experiment needs more data before it can be read on the slice alone.",
    ]
    return out, info


def report_markdown(topic: str | None = None, release: bool = False, today: str | None = None,
                    sha: str | None = None, holdout_log: Path | None = None) -> str:  # fmt: skip

    topic = topic or weakest_slice()
    if topic not in topics():
        raise ValueError(f"unknown topic {topic!r}; choose one of {', '.join(topics())}")
    today = today or datetime.now().astimezone().strftime("%Y-%m-%d")
    s2, s3, s4, s5, s6 = m02(), m03(), m04(), m05(), m06()
    s7, s8, s9, s10, s11 = m07(), m08(), m09(), m10(), m11()
    d = s11["decision"]
    cand = d.chosen
    S = s11["summaries"]
    b, c = S[BASELINE], S[cand]
    ov = s11["overall"]
    ho = holdout_look(topic, holdout_log) if release else None
    slice_md, sl = _slice_section(topic, ho)
    cps_change = c.cost_per_success / b.cost_per_success - 1
    ef = s9["alarms"]["evidence_fail"]
    seg = s9["segments"]
    new_ver = max(seg, key=lambda v: seg[v][0] / max(1, seg[v][1]))
    old_ver = min(seg, key=lambda v: seg[v][0] / max(1, seg[v][1]))
    asr2, fpr2 = s10["asr"]["v2"], s10["fpr"]["v2"]
    worst_vec = max(s10["vectors"], key=lambda vr: vr[1][-1].p)
    sc = s11["selfcheck"]
    ship = ov.low > 0 and ho is not None and ho.paired.diff >= 0
    L: list[str] = []
    add = L.append

    add(f"# MediaDoctor eval report: replace `{BASELINE}` with `{cand}`?")
    add("")
    add(f"**Date:** {today} · **Author:** the course (reference report for [module 12]({mods(12)})) · "
        f"**Slice:** {topic} · **Held-out look:** {'spent (release run)' if ho else 'not spent (dev only)'}")  # fmt: skip
    add("")
    add('!!! info "Synthetic-authored model behaviour, real everything else"')
    add(
        "    The model turns, token counts, and latencies in every fixture this report reads were written by the"
    )
    add(
        "    course's `scripts/author_module*_fixtures.py` scripts and are labelled `synthetic-authored`. The numbers"
    )
    add(
        "    show what the method produces; they make no claim about how Claude models behave on your system. The"
    )
    add(
        "    agent loop, tools, checks, judge prompts, prices, and statistics are real code, and this page is"
    )
    add("    regenerated from them by `uv run mediadoctor-capstone report`.")
    add("")

    # 1
    add("## 1. Decision requested")
    add("")
    kept = " → ".join(f"`{k}`" for k in d.kept)
    add(f"Approve `{cand}` as the release configuration in `config/release.toml`, in place of `{BASELINE}`. "
        f"`{cand}` is the end of a chain of changes that each passed its own pre-registered test ({kept}; "
        f"section 7). Separately, fund the follow-ups in section 9, starting with the app {new_ver} evidence "
        f"regression and the {topic} slice.")  # fmt: skip
    add("")

    # 2
    add("## 2. Summary")
    add("")
    if ho:
        # Lead with the held-out number: the dev number comes from the queries every step was chosen on,
        # so it is biased upward (selection, and five sequential keep-or-drop decisions).
        add(f"- **Better answers.** On the {ho.n} held-out queries, read once and never used to choose: "
            f"`{cand}` {rate(ho.cand, ho.n)} against {rate(ho.base, ho.n)} for `{BASELINE}`, a difference of "
            f"{diff(ho.paired)}: the unbiased estimate, and too few queries to pin the size down. On the {b.n} "
            f"dev queries every step was chosen on, {rate(c.successes, c.n)} against {rate(b.successes, b.n)}, "
            f"{diff(ov)} ({ov.b_only} fixed, {ov.a_only} broken); optimistic, because the configuration was "
            "selected on them.")  # fmt: skip
    else:
        add(f"- **Better answers.** On the {b.n} dev queries, `{cand}` succeeds on {rate(c.successes, c.n)} "
            f"against {rate(b.successes, b.n)} for `{BASELINE}`: a paired difference of {diff(ov)} "
            f"({ov.b_only} queries fixed, {ov.a_only} broken). This is the set every step was chosen on, so it "
            "is optimistic; the held-out split has not been read yet (run with `--release` once).")  # fmt: skip
    add(f"- **Cheaper per successful task.** {money(c.cost_per_success)} {ci_money(c.cps_low, c.cps_high)} "
        f"against {money(b.cost_per_success)} {ci_money(b.cps_low, b.cps_high)}, a change of "
        f"{cps_change:+.0%}; p95 latency {c.p95_ms / 1000:.1f} s [{c.p95_low / 1000:.1f}, {c.p95_high / 1000:.1f}] "
        f"against {b.p95_ms / 1000:.1f} s, inside the 12 s guardrail.")  # fmt: skip
    add(f"- **Not a fix for everything.** Production monitoring shows evidence failures at "
        f"{seg[new_ver][0] / seg[new_ver][1]:.1%} on app {new_ver} against {seg[old_ver][0] / seg[old_ver][1]:.1%} "
        f"on {old_ver} (CUSUM alarm {ef.hours_after_rollout:.1f} h after the rollout), which this change does not "
        f"address; the {topic} slice is the weakest topic under `{cand}` at "
        f"{rate(sum(dev_rows(cand)[i].success for i in sl['ids']), len(sl['ids']))}.")  # fmt: skip
    add("")

    # 3
    add("## 3. Scope")
    add("")
    v = X.variants()
    add(table(
        ["Item", "Value"],
        [
            ["System", "MediaDoctor, the course's Android and multimedia debugging agent (tool-calling, with KB retrieval)"],
            ["Baseline", f"`{BASELINE}`: {v[BASELINE].model}, prompt {v[BASELINE].prompt}, no caching, single attempt"],
            ["Candidate", f"`{cand}`: {v[cand].model}, prompt {v[cand].prompt}, caching "
                          f"{'on' if v[cand].cache else 'off'}, strategy {v[cand].strategy}"],
            ["Judges", "Haiku 5.5 (`claude-haiku-5-5`) for every LLM judge and the self-check"],
            ["Prompt versions", "agent v1, v2, v3 (`mediadoctor.experiments.PROMPTS`); judges as validated in module 5"],
            ["Dates", f"experiments pre-registered and run 2026-11-23; production window "
                      f"{s9['days'][0].date} to {s9['days'][-1].date}; report {today}"],
            ["Out of scope", "real user traffic (all data is synthetic-authored), languages other than English, "
                             "load and concurrency, multi-turn chat beyond module 7's simulated sessions, "
                             "modes module 11 did not label (see section 8)"],
        ],
    ))  # fmt: skip
    add("")

    # 4
    add("## 4. Data")
    add("")
    sp = s4["splits"]
    add(table(
        ["Set", "Size", "How it was built", "Used for"],
        [
            ["Module 1 smoke set", "20 queries", "hand-written", "the first baseline and code checks"],
            ["Module 3 traces", f"{s3['n']} traces", "synthetic-authored agent runs, open and axial coded",
             "the failure taxonomy"],
            ["Module 4 dataset v1", f"{s4['n']} queries (train {sp['train']}, dev {sp['dev']}, test {sp['test']})",
             "dimension tuples → LLM-written queries, checked and deduplicated", "judges, stats, experiments"],
            ["Golden set", f"{s8['manifest']}, {s8['n_files']} files", "module 8 manifest with hashes and splits",
             "the CI gate"],
            ["Experiment cases", f"{b.n} dev + {n_holdout()} held out", "module 5's agent slice of dataset v1",
             "this decision"],
            ["Module 7 retrieval set", "48 labelled queries, 57 KB sections", "hand-labelled relevance",
             "the architecture-specific eval"],
            ["Module 9 traffic", f"{s9['n']} requests over {len(s9['days'])} days", "simulated production with a "
             "rollout and a model snapshot change", "monitoring"],
            ["Module 10 suites", f"{s10['asr']['none'].n} attacks, {s10['fpr']['none'].n} benign requests",
             "authored attacks over five vectors, plus hard negatives", "red-teaming"],
        ],
    ))  # fmt: skip
    add("")
    cov = s4["coverage"]
    add(f"**Coverage gaps.** Dataset v1 covers {s4['all'][0]}/{s4['all'][1]} feasible pairs of dimension values "
        f"overall, but the dev split alone covers {cov['dev'][0]}/{cov['dev'][1]} and test {cov['test'][0]}/"
        f"{cov['test'][1]}, so some combinations are only ever seen in training. Every query is synthetic: the "
        "phrasing of real support tickets, real devices outside the course's device table, and non-English "
        "questions are not represented.")  # fmt: skip
    add("")

    # 5
    add("## 5. Failure taxonomy")
    add("")
    add(f"From [module 3]({mods(3)})'s {s3['n']} coded traces of `{BASELINE}` ({s3['failing']} failing), ranked by "
        "count × severity:")  # fmt: skip
    add("")
    add(table(
        ["#", "Failure mode", "Traces", "Rate (k/n) [95% CI]", "Severity", "Fix", "Example trace"],
        [[r.rank, r.mode.id, r.count, rate(r.count, s3["n"]), r.mode.severity,
          r.mode.fixability, f"`{r.examples[0]}`" if r.examples else "-"] for r in s3["ranked"]],
    ))  # fmt: skip
    add("")
    add("**Before and after,** for the four modes module 11's reference labels record in final answers (dev, "
        f"n = {b.n}; paired difference in the share of queries with the mode):")  # fmt: skip
    add("")
    labs = labels()
    ids = dev_ids()
    mrows = []
    for code in ("premise", "ignored", "skipped", "format"):
        a = [labs[(BASELINE, i)] == code for i in ids]
        bb = [labs[(cand, i)] == code for i in ids]
        p = paired_bootstrap_diff(a, bb, seed=11)
        mrows.append([MODE_NAMES[code], rate(sum(a), len(a)), rate(sum(bb), len(bb)), diff(p)])
    add(table(["Mode", BASELINE, cand, "Change [95% CI]"], mrows))
    add("")
    up = ", ".join(f"{k} {n}" for k, n in s3["upstream"].most_common(4))
    add(f"Where the first failure happens in a failing trace (module 3): {up}. Most failures start in the model's "
        "final answer or its plan, not in the tools, which is why the improvements in section 7 are prompt and "
        "self-check changes.")  # fmt: skip
    add("")

    # 6
    add("## 6. Evaluators")
    add("")
    add("Every judge was validated against human labels on a split it was not tuned on. PASS is the positive "
        "class: TPR is the share of good answers the judge passes, TNR the share of bad answers it fails.")  # fmt: skip
    add("")
    erows = []
    for name, val in s5["judges"].items():
        r = val.result
        erows.append([f"`{name}@{s5['versions'][name]}` judge", "module 5", f"test, n={r.n}",
                      f"{r.tpr:.2f} ({r.tp}/{r.tp + r.fn})", f"{r.tnr:.2f} ({r.tn}/{r.tn + r.fp})"])  # fmt: skip
    for name, key in (("faithfulness", "faithfulness"), ("answer relevance", "relevance")):
        r = s7[key]
        erows.append([f"RAG {name} judge", "module 7", f"n={r.n}", f"{r.tpr:.2f} ({r.tp}/{r.tp + r.fn})",
                      f"{r.tnr:.2f} ({r.tn}/{r.tn + r.fp})"])  # fmt: skip
    good, bad = sc.tn + sc.fp, sc.tp + sc.fn
    erows.append(["Self-check judge (the retry step)", "module 11", f"dev first answers, n={good + bad}",
                  f"{sc.tn / good:.2f} ({sc.tn}/{good})", f"{sc.tp / bad:.2f} ({sc.tp}/{bad})"])  # fmt: skip
    det = s10["detector"]
    erows.append(["Injection detector (guardrails v2)", "module 10", f"screened texts, n={det.tp + det.fn + det.tn + det.fp}",
                  f"flags {det.tpr:.2f} of injections ({det.tp}/{det.tp + det.fn})",
                  f"passes {det.tnr:.2f} of clean texts ({det.tn}/{det.tn + det.fp})"])  # fmt: skip
    add(table(["Evaluator", "Built in", "Validated on", "TPR", "TNR"], erows))
    add("")
    add("Code checks need no validation set of their own but were checked against the same labels: format, "
        "citations (every cited KB id exists), investigated (a tool ran before the answer), and the reference "
        "check of the diagnosis. Trace checks from module 2 (evidence is real, no repeated retrieval, step "
        f"budget) pass on {', '.join(f'{k} {v[0]}/{v[1]}' for k, v in s2['checks'].items())} of the module 2 "
        "traces.")  # fmt: skip
    add("")
    est = s5["estimate"]
    add(f"**Judge error changes the numbers you report.** The tool-grounding judge's raw pass rate on "
        f"{est.n_unlabelled} unlabelled traces is {est.observed:.3f}; corrected for its TPR and TNR it is "
        f"{est.corrected:.3f} {ci(est.low, est.high)} (the reference labels say {s5['truth']:.3f}). The corrected "
        "interval is wide because the judge was validated on only "
        f"{est.n_labelled} labelled traces: more labels, not a better prompt, is what narrows it.")  # fmt: skip
    add("")

    # 7
    add("## 7. Results")
    add("")
    add(f"### Configurations on dev (n = {b.n})")
    add("")
    add("Each kept change was tested against its parent with a rule written down before the run "
        "(`config/experiments/preregistration.toml`). Success means all four checks pass within the 15 s timeout.")  # fmt: skip
    add("")
    crow = []
    for n_, s in S.items():
        verdict = d.verdicts.get(n_, ("baseline", ""))[0]
        crow.append([f"`{n_}`", rate(s.successes, s.n), f"{s.p50_ms / 1000:.2f}", f"{s.p95_ms / 1000:.2f}",
                     money(s.cost_per_task), f"{money(s.cost_per_success)} {ci_money(s.cps_low, s.cps_high)}",
                     verdict])  # fmt: skip
    add(table(["Configuration", "Success [95% CI]", "p50 s", "p95 s", "Cost/task", "Cost/success [95% CI]",
               "Verdict"], crow))  # fmt: skip
    add("")
    add("Each kept step against its parent (paired, same queries):")
    add("")
    add(table(["Step", "Change", "Difference [95% CI]", "Fixed / broken", "McNemar p"],
              [[f"`{a}` → `{bn}`", v[bn].change.split(":")[0], diff(p), f"{p.b_only} / {p.a_only}",
                f"{p.p_value:.3f}"] for a, bn, p in s11["chain"]]))  # fmt: skip
    add("")
    if ho:
        add(f"**Held-out confirmation** (read once, logged in `{HOLDOUT_LOG.as_posix()}`): `{BASELINE}` "
            f"{rate(ho.base, ho.n)}, `{cand}` {rate(ho.cand, ho.n)}, paired difference {diff(ho.paired)} "
            f"({ho.paired.b_only} fixed, {ho.paired.a_only} broken, McNemar p = {ho.paired.p_value:.2f}).")  # fmt: skip
        add("")

    add("### Per-case diff")
    add("")
    fixed = [i for i in ids if dev_rows(cand)[i].success and not dev_rows(BASELINE)[i].success]
    broken = [i for i in ids if dev_rows(BASELINE)[i].success and not dev_rows(cand)[i].success]
    add(f"`{BASELINE}` → `{cand}` fixed {len(fixed)} queries and broke {len(broken)}. Fixed, by the baseline's "
        "failure: " + ", ".join(f"{k} {n}" for k, n in Counter(base_mode(i) for i in fixed).most_common()) + ".")  # fmt: skip
    add("")
    add(table(["Case", "Topic", f"{BASELINE} mode", f"{cand} answer (first line)"],
              [[f"`{i}`", case_by_id()[i]["topic"], base_mode(i),
                _answer_line(cand, i)] for i in fixed[:5]]))  # fmt: skip
    add("")
    add(
        f"(First five of {len(fixed)}; `uv run mediadoctor-lab11 trace {cand} CASE` shows any of them.)"
    )
    add("")

    add("### Latency and cost from traces")
    add("")
    lrows = []
    for n_ in (BASELINE, cand):
        rs = list(dev_rows(n_).values())
        lat = [r.latency_ms for r in rs]
        cost = [r.cost_usd for r in rs]
        lrows.append([f"`{n_}`", f"{percentile(lat, 0.5) / 1000:.2f} s", f"{percentile(lat, 0.9) / 1000:.2f} s",
                      money(percentile(cost, 0.5)), money(percentile(cost, 0.9)),
                      ", ".join(f"`{r.case_id}` {money(r.cost_usd)}" for r in
                                sorted(rs, key=lambda r: (-r.cost_usd, r.case_id))[:3])])  # fmt: skip
    add(table(["Configuration", "Median latency", "p90 latency", "Median cost", "p90 cost",
               "Most expensive traces"], lrows))  # fmt: skip
    add("")
    add(f"`{cand}` retried {c.retried} of {c.n} tasks; those carry the extra latency. Cache hit rate "
        f"{c.cache_hit_rate:.0%} of input tokens.")  # fmt: skip
    add("")

    add("### Trace checks next to answer quality")
    add("")
    trows = []
    for chk in X.CHECKS:
        trows.append([chk] + [rate(sum(dict(dev_rows(n_)[i].checks)[chk] for i in ids), len(ids))
                              for n_ in (BASELINE, cand)])  # fmt: skip
    add(table(["Check", BASELINE, cand], trows))
    add("")

    add("### Architecture-specific eval: retrieval and RAG (module 7)")
    add("")
    add(table(["Retrieval config", "recall@5 [95% CI]", "MRR", "nDCG"],
              [[k, f"{r['recall'][0]:.3f} {ci(r['recall'][1], r['recall'][2])}", f"{r['mrr']:.2f}",
                f"{r['ndcg']:.2f}"] for k, r in s7["retrieval"].items()]))  # fmt: skip
    rd = s7["recall_diff"]
    rp = s7["rag_paired"]
    att = s7["attribution"]
    add("")
    add(f"Section chunking with BM25 improves recall@5 by {rd[0]:+.3f} {ci(rd[1], rd[2], signed=True)} "
        f"(n = {rd[3]}). End to end, the improved RAG answers are correct and faithful on "
        f"{rp.rate_b:.3f} against {rp.rate_a:.3f} ({diff(rp)})"
        + (": retrieval got better, but the end-to-end interval includes zero. " if rp.low <= 0 else ". ")
        + f"Attribution of the improved system's failures: {att['generation failure']} generation, "
        f"{att['retrieval failure']} retrieval"
        + (", so a generation fix is worth more than more retrieval work." if att["generation failure"] >
           att["retrieval failure"] else ", so retrieval is still the bigger lever."))  # fmt: skip
    add("")

    add("### Statistics that qualify the headline (module 6)")
    add("")
    t = s6["trials"]
    add(f"Five repeated runs of v2 on {t.n_cases} queries: run pass rates "
        f"{', '.join(f'{x:.2f}' for x in t.run_rates)}; {t.always_pass} always pass, {t.never_pass} never pass, "
        f"and {s6['flaky']} are flaky. One run of a configuration is one draw: module 11's fixtures pin one draw "
        "per query, so the dev differences above are conditional on it.")  # fmt: skip
    add("")

    add("### CI gate (module 8)")
    add("")
    add(f"The release configuration passes its gate against the committed baseline ({s8['status']}: code tier "
        f"{s8['tiers']['code']}, judge tier {s8['tiers']['judges']}); the golden manifest has "
        f"{len(s8['manifest_problems'])} problems. Switching `config/release.toml` to `{cand}` will change the "
        "request keys, so the pull request must re-record the gate fixtures and update `evals/baseline.json`.")  # fmt: skip
    add("")

    add("### Monitoring (module 9)")
    add("")
    mrows = []
    for m, a in s9["alarms"].items():
        mrows.append([m, f"{a.p0:.1%}", a.when.strftime("%a %d %b %H:%M IST") if a.when else "no alarm",
                      f"{a.hours_after_rollout:+.1f} h" if a.when else "-"])  # fmt: skip
    add(table(["Signal", "Reference rate", "CUSUM alarm", "After rollout"], mrows))
    add("")
    tseg = s9["tool_segments"]
    add(f"After the rollout, by app version: evidence failures {rate(*seg[old_ver])} on {old_ver} and "
        f"{rate(*seg[new_ver])} on {new_ver}; tool errors {rate(*tseg[old_ver])} and {rate(*tseg[new_ver])}.")  # fmt: skip
    add("")

    add("### Red team (module 10)")
    add("")
    add(table(["Guardrails", "Attack success rate [95% CI]", "Benign false-positive rate [95% CI]"],
              [[g, str(s10["asr"][g]), str(s10["fpr"][g])] for g in ("none", "v1", "v2")]))  # fmt: skip
    add("")
    add(f"The weakest vector under v2 is `{worst_vec[0]}` at {worst_vec[1][-1]}.")
    add("")
    add("### Slice deep-dive")
    add("")
    add(table(["Topic", "n", BASELINE, cand, "Paired difference [95% CI]"],
              [[r["topic"], r["n"], f"{r['base'] / r['n']:.3f}", f"{r['cand'] / r['n']:.3f}", diff(r["paired"])]
               for r in slice_rows()]))  # fmt: skip
    add("")
    L.extend(slice_md)
    add("")

    # 8
    add("## 8. Risks and caveats")
    add("")
    risks = [
        "**Synthetic data.** Every fixture is synthetic-authored. The method transfers; the rates do not. "
        "Re-record live (module 12, *Make it your own*) before using any number for a real decision.",
        f"**Sample size.** {b.n} dev queries detect a paired change of about "
        f"{mdd_paired(b.n, max((ov.a_only + ov.b_only) / b.n, 0.2)):.2f}; the {topic} slice "
        f"({len(sl['ids'])} queries) "
        + (
            f"about {sl['mdd']:.2f}"
            if sl["mdd"] == sl["mdd"]
            else "cannot detect anything smaller than its discordant share"
        )
        + ". A step can be detected below that size only when almost every query that changed moved the same "
        f"way: the last step, {diff(s11['chain'][-1][2])}, rests on {s11['chain'][-1][2].b_only} fixed and "
        f"{s11['chain'][-1][2].a_only} broken queries.",
        f"**The last step's test.** `{s11['chain'][-1][1]}` was kept by the pre-registered rule (a paired "
        f"bootstrap interval above zero), but it rests on {s11['chain'][-1][2].a_only + s11['chain'][-1][2].b_only} "
        f"changed queries, and the exact McNemar p is {s11['chain'][-1][2].p_value:.2f}. Module 6 trusts the exact "
        "test below about 10 changed queries; amendment 1 of the pre-registration requires it from the next study "
        "on. Read the last step as likely, not proven, and confirm it on more queries.",
        f"**Judge error.** The self-check judge fails {sc.fp} good first answers and passes {sc.fn} bad ones on dev; "
        "the other judges' TNRs (section 6) are lower than their TPRs, so raw judge pass rates overstate quality.",
        "**Metric definitions differ across modules.** Module 6 grades all human-labelled failure modes "
        f"(v1 → v2 {diff(s6['paired'])}); module 11 grades four checks (v1 → v2 "
        f"{diff(s11['chain'][0][2])}). They answer different questions; do not quote one as the other.",
        "**Modes not tracked after the change.** Module 11's labels cover four modes. Fabricated evidence, "
        "wrong tool arguments, wrong API details, and retrieval misses (modules 3 and 7) were not re-measured "
        f"for `{cand}`.",
        f"**Distribution shift.** Production traffic after the {new_ver} rollout differs from the dev set "
        "(more AV1, a new device); the dev results say nothing about it.",
        f"**Latency headroom.** p95 {c.p95_ms / 1000:.1f} s with an upper CI of {c.p95_high / 1000:.1f} s against a "
        "12 s guardrail.",
        f"**Security.** Guardrails v2 still let {asr2.k} of {asr2.n} attacks through and refuse {fpr2.k} of "
        f"{fpr2.n} benign requests; the suite has {asr2.n} cases, so a 0% observed rate would still allow an "
        f"upper bound near {wilson_interval(0, asr2.n)[1]:.0%}.",
    ]
    L.extend(f"- {r}" for r in risks)
    add("")

    # 9
    add("## 9. Recommendation and next steps")
    add("")
    if ship:
        add(f"**Ship `{cand}`.** It is better on dev with an interval that excludes zero, and the one held-out "
            f"look points the same way ({diff(ho.paired)}; with {ho.n} queries it is a check for a reversal, "
            "not a second significance test). It is also cheaper per successful task. Ship it behind module 8's "
            "gate, with module 9's monitors unchanged, and watch p95 latency for the first week.")  # fmt: skip
    elif ov.low > 0 and ho is None:
        add(f"**Ship `{cand}` once the held-out look agrees.** It is better on dev with an interval that "
            "excludes zero; run this report once with `--release` before changing `config/release.toml`.")  # fmt: skip
    else:
        add(f"**Do not ship `{cand}` yet.** Either the dev interval includes zero or the held-out look "
            "reversed the direction; see section 7.")  # fmt: skip
    add("")
    steps = [
        f"Investigate the evidence-failure regression on app {new_ver} before rollout widens (owner: app team; "
        "module 9's dashboard is the success measure).",
        f"Close the `{worst_vec[0]}` injection vector (module 10), then re-run the red-team gate.",
        f"{topic}: the top remaining mode is "
        f"{MODE_NAMES.get(sl['top_mode'], sl['top_mode']) if sl['top_mode'] else 'none'}. Pre-register a "
        f"slice-specific fix, and write about {sl['need']} more {topic} queries (module 4) so the experiment can "
        "be read on the slice.",
        "Re-label a sample of the candidate's answers for the modes module 11 did not track (section 8).",
        "Rotate the held-out split (module 8's `rotate`) now that it has been read for this decision.",
    ]
    L.extend(f"{i}. {s}" for i, s in enumerate(steps, 1))
    add("")

    # 10
    add("## 10. Appendix")
    add("")
    add(f"- **Code version:** {f'`{sha}`' if sha else '`git log -1 --format=%H -- docs/capstone/index.md` (the commit that published this page)'}")  # fmt: skip
    add(
        f"- **Inputs fingerprint:** `{inputs_fingerprint()}` (sha256 of `fixtures/recorded`, `data`, and `config`)"
    )
    add(f"- **Golden set:** {s8['manifest']}")
    add("- **Reproduce:**")
    add("")
    add("```bash")
    args = f" --slice {topic}" + (" --release" if release else "") + f" --date {today}"
    add(f"uv run mediadoctor-capstone report{args} --out runs/capstone/report.md")
    add("uv run mediadoctor-capstone run         # the stage summary")
    add(
        f"uv run mediadoctor-lab11 trace {cand} {fixed[0] if fixed else ids[0]}   # any quoted trace"
    )
    add("```")
    add("")
    add("- **Trace and case ids quoted in this report:** "
        + ", ".join(f"`{i}`" for i in sorted(set(fixed[:5]) | set(sl["still"])))
        + "; module 3 examples " + ", ".join(f"`{r.examples[0]}`" for r in s3["ranked"] if r.examples)
        + "; module 9 alarms at requests "
        + ", ".join(f"`{a.at}`" for a in s9["alarms"].values() if a.when) + ".")  # fmt: skip
    add("- **Where each number comes from:** " + ", ".join(
        f"[module {n}]({mods(n)})" for n in range(1, 12)) + ".")  # fmt: skip
    return "\n".join(L) + "\n"


def selfcheck_fixed() -> str:
    sc = m11()["selfcheck"]
    return f"{sc.fixed} of {sc.retried}"


def n_holdout() -> int:
    from mediadoctor import lab11

    return len(lab11.split_cases("holdout"))  # a count only: no outcomes are read


def base_mode(cid: str) -> str:
    """The baseline's failure on a dev case: a labelled mode, or why a correct answer still failed."""
    m = labels()[(BASELINE, cid)]
    if m != "none":
        return MODE_NAMES.get(m, m)
    return "timed out" if dev_rows(BASELINE)[cid].timed_out else "a check failed"


def ci_money(lo: float, hi: float) -> str:
    return f"[{money(lo)}, {money(hi)}]"


# --- self-review ------------------------------------------------------------------------------------------


def check_report(text: str) -> list[str]:
    """Problems a reviewer would flag before reading the content: missing sections, bare rates, no repro."""
    problems = []
    heads = re.findall(r"^## (?:\d+\.\s*)?(.+)$", text, flags=re.M)
    for s in SECTIONS:
        if not any(h.strip().lower().startswith(s.lower()) for h in heads):
            problems.append(f"missing section: {s}")
    summary = re.search(r"^## (?:\d+\.\s*)?Summary\s*$(.*?)^## ", text, flags=re.M | re.S)
    if summary:
        bullets = [ln for ln in summary.group(1).splitlines() if ln.startswith("- ")]
        if len(bullets) != 3:
            problems.append(f"summary has {len(bullets)} bullets; the template asks for 3")
        for i, bl in enumerate(bullets, 1):
            if not re.search(r"\[[-+]?\d", bl):
                problems.append(f"summary bullet {i} has a number without an interval")
    if "TPR" not in text or "TNR" not in text:
        problems.append("no judge validation (TPR and TNR)")
    if "uv run" not in text:
        problems.append("appendix has no command to reproduce the numbers")
    if "synthetic" not in text.lower():
        problems.append("no statement of where the data came from (real or synthetic)")
    return problems


# --- CLI --------------------------------------------------------------------------------------------------


def _write(text: str, out: str | None) -> None:
    if not out:
        print(text, end="")
        return
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mediadoctor-capstone", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="replay every module's stage and print one line each")
    sub.add_parser("slices", help="baseline vs candidate per topic")
    sp = sub.add_parser("report", help="the full eval report as Markdown")
    sp.add_argument(
        "--slice", choices=topics(), help="topic for the deep-dive (default: the weakest)"
    )
    sp.add_argument("--release", action="store_true", help="spend the one held-out look (logged)")
    sp.add_argument("--date", help="report date, YYYY-MM-DD (default: today)")
    sp.add_argument("--sha", help="git commit to name in the appendix")
    sp.add_argument("--out")
    sp = sub.add_parser("check", help="check a report against the eval report template")
    sp.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        rows = stages()
        print(render_stages(rows))
        flagged = [s for s in rows if not s.ok]
        print(f"\n{len(rows)} stages replayed; {len(flagged)} flagged for the report")
    elif a.cmd == "slices":
        print(render_slices())
    elif a.cmd == "report":
        _write(report_markdown(a.slice, a.release, a.date, a.sha), a.out)
    elif a.cmd == "check":
        problems = check_report(Path(a.file).read_text(encoding="utf-8"))
        for p in problems:
            print(f"  {p}")
        print(f"{a.file}: {'ok' if not problems else f'{len(problems)} problems'}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
