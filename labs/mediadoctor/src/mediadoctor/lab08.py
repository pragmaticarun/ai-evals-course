"""Module 8 lab: CI/CD for MediaDoctor's evals.

    uv run mediadoctor-lab08 preflight [--prompt v2]      # replay misses before running anything
    uv run mediadoctor-lab08 run --prompt v2 --tier all --out runs/v2.json
    uv run mediadoctor-lab08 diff runs/v1.json runs/v2.json [--out runs/diff.md]
    uv run mediadoctor-lab08 gate [--base-ref main] [--tier code|judges] [--summary FILE]
    uv run mediadoctor-lab08 baseline --check | --write   # evals/baseline.json vs the release config
    uv run mediadoctor-lab08 manifest --check | --write   # data/golden/manifest.json
    uv run mediadoctor-lab08 hygiene                      # leakage, contamination, stale labels
    uv run mediadoctor-lab08 budget                       # replay time and live re-record cost
    uv run mediadoctor-lab08 release [--prompt v2] [--log]  # the held-out split (release decisions)
    uv run mediadoctor-lab08 naive                        # fixed thresholds vs the paired gate

Everything replays from fixtures and needs no API key. The agent runs are module 5's (prompt v1) and
module 6's (prompt v2); the judge verdicts on v2's dev answers are synthetic-authored
(scripts/author_module08_fixtures.py), the rest are module 5's.

Exit codes of `gate`: 0 pass (or pass with warnings), 1 blocked by a regression, 3 replay misses
(the change needs re-recorded fixtures before it can be evaluated).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import (
    LLM,
    FixtureMissingError,
    Mode,
    Tracer,
    load_prices,
    repo_root,
    request_key,
    text_of,
)
from evalkit.config import apply_generation
from evalkit.fixtures import canonical_json
from evalkit.gate import (
    ICON,
    Budget,
    GateResult,
    GateRule,
    Status,
    Usage,
    budget_problems,
    describe,
    evaluate_gate,
    flips,
    naive_gate,
)
from evalkit.golden import (
    HoldoutGuard,
    build_manifest,
    check_manifest,
    load_manifest,
    write_manifest,
)
from evalkit.hygiene import cross_split_pairs, ngram_contamination, stale_labels, text_digest
from evalkit.judge import Item, build_judge_request, leakage_problems, parse_verdict, render_item
from evalkit.stats import pass_rate
from evalkit.synth import prose
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from mediadoctor import lab03, lab04, lab05, lab06
from mediadoctor.toolagent import AGENT_PROMPTS, build_request, run_agent

# New recordings go to the first namespace; replay also finds module 5's (v1) and module 6's (v2) runs.
AGENT_NAMESPACES = ("mediadoctor-m8-agent", lab05.AGENT_NAMESPACE, lab06.AGENT_NAMESPACE)
JUDGE_NAMESPACE = "mediadoctor-m8-judges"
JUDGE_NAMESPACES = (JUDGE_NAMESPACE, lab05.JUDGE_NAMESPACE)
RUN_SCHEMA = "mediadoctor-eval-run/1"
TIERS = ("code", "judges")
GOLDEN_NAME = "mediadoctor-golden"
GOLDEN_VERSION = "1.0.1"
HOLDOUT_SPLIT = "test"

Trace = list[dict[str, Any]]


def rel(path: Path) -> str:
    return path.relative_to(repo_root()).as_posix()


# --- Configuration ------------------------------------------------------------------------------------


def release_path() -> Path:
    return repo_root() / "config" / "release.toml"


def gate_config_path() -> Path:
    return repo_root() / "config" / "eval_gate.toml"


@cache
def gate_config() -> dict[str, Any]:
    return tomllib.loads(gate_config_path().read_text(encoding="utf-8"))


def gate_rule() -> GateRule:
    r = gate_config()["rule"]
    return GateRule(
        alpha=r["alpha"],
        margin=r["margin"],
        min_effect=r["min_effect"],
        draws=r["draws"],
        seed=r["seed"],
    )


def budget() -> Budget:
    b = gate_config()["budget"]
    return Budget(b["replay_seconds"], b["live_usd"], b["live_minutes"], b["concurrency"])


def manifest_path() -> Path:
    return repo_root() / gate_config()["golden"]["manifest"]


def baseline_path() -> Path:
    return repo_root() / gate_config()["golden"]["baseline"]


def label_answers_path() -> Path:
    return repo_root() / "data" / "golden" / "label_answers.csv"


def holdout_log_path() -> Path:
    return repo_root() / "data" / "golden" / "holdout_log.csv"


def release_prompt(text: str | None = None) -> str:
    """The prompt version in config/release.toml (or in `text`, the file's content at another ref)."""
    data = tomllib.loads(text if text is not None else release_path().read_text(encoding="utf-8"))
    return data["agent"]["prompt"]


def fingerprint(prompt: str) -> str:
    """Everything about the agent's requests except the conversation: model, limits, generation
    settings (thinking, effort), prompt, tools."""
    req = apply_generation(build_request([], prompt))
    req.pop("messages")
    return hashlib.sha256(canonical_json(req).encode()).hexdigest()[:12]


# --- The golden dataset and its splits ---------------------------------------------------------------


@cache
def rows() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in lab05.label_rows()}


def split_of() -> dict[str, str]:
    return {cid: r["split"] for cid, r in rows().items()}


def ids_in(splits: Iterable[str]) -> list[str]:
    wanted = set(splits)
    return sorted(cid for cid, s in split_of().items() if s in wanted)


def tier_splits(tier: str) -> list[str]:
    return list(gate_config()["tiers"][tier]["splits"])


def holdout_ids() -> list[str]:
    return ids_in([HOLDOUT_SPLIT])


def guard() -> HoldoutGuard:
    return HoldoutGuard(frozenset(holdout_ids()))


def golden_files() -> list[str]:
    root = repo_root()
    files = [
        rel(lab04.dataset_path()),
        rel(lab05.labels_path()),
        rel(lab06.labels_path()),
        rel(label_answers_path()),
        "data/golden/hygiene_review.csv",
        *(
            rel(lab05.spec_path(j, lab05.FINAL[j]))
            for j in gate_config()["tiers"]["judges"]["judges"]
        ),
        *(f"fixtures/recorded/{ns}.jsonl" for ns in (*AGENT_NAMESPACES, *JUDGE_NAMESPACES)),
    ]
    return [f for f in files if (root / f).is_file()]


def golden_splits() -> dict[str, list[str]]:
    return {
        "gate": ids_in(tier_splits("code")),
        "judges": ids_in(tier_splits("judges")),
        "holdout": holdout_ids(),
    }


def make_manifest(created: str | None = None) -> dict[str, Any]:
    return build_manifest(
        GOLDEN_NAME,
        GOLDEN_VERSION,
        repo_root(),
        golden_files(),
        golden_splits(),
        created=created or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        source="dataset v1 (module 4), reference labels (modules 5 and 6), recorded runs",
        notes="Bump the version when any file changes: major for new cases or splits, "
        "minor for relabels or re-recorded runs, patch for fixes that change no outcome.",
    )


def manifest_problems() -> list[str]:
    return check_manifest(load_manifest(manifest_path()), repo_root(), golden_splits())


# --- Replay -------------------------------------------------------------------------------------------


MIN_PLAUSIBLE_MS = 50.0  # module 5's judge records carry no real latency (they were scripted)


def estimated_latency_ms(input_tokens: int, output_tokens: int) -> float:
    """A rough latency model for budgeting when no latency was recorded: 0.4 s to first token,
    plus 0.04 ms per input token and 14 ms per output token."""
    return 400 + 0.04 * input_tokens + 14 * output_tokens


class ReplayChain:
    """An LLM that replays from several fixture namespaces in turn and adds up what the calls cost.

    Fixture keys are content hashes, so a request recorded for one module replays in another. Record
    and live modes write to (and call through) the first namespace.
    """

    def __init__(self, namespaces: Sequence[str], mode: Mode | str | None = None):
        self.llms = [LLM(namespace=ns, mode=mode) for ns in namespaces]
        self.mode = self.llms[0].mode
        self.namespaces = tuple(namespaces)
        self.last_latency_ms: float | None = None
        self.last_replayed = False
        self.usage = Usage()
        self.estimated = 0  # calls whose recorded latency was missing, so it was estimated
        self._prices = load_prices()

    def has(self, request: dict[str, Any]) -> bool:
        return any(llm.store.has(request) for llm in self.llms)

    def create(self, **request: Any) -> dict[str, Any]:
        llms = self.llms if self.mode is Mode.REPLAY else self.llms[:1]
        for llm in llms:
            try:
                resp = llm.create(**request)
            except FixtureMissingError:
                continue
            self.last_latency_ms, self.last_replayed = llm.last_latency_ms, llm.last_replayed
            u = resp.get("usage", {})
            tin, tout = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
            price = self._prices.get(str(resp.get("model") or request.get("model")))
            latency_ms = llm.last_latency_ms
            if not latency_ms or latency_ms < MIN_PLAUSIBLE_MS:
                latency_ms = estimated_latency_ms(tin, tout)
                self.estimated += 1
            self.usage += Usage(
                1, tin, tout, price.cost_usd(tin, tout) if price else 0.0, latency_ms / 1000
            )
            return resp
        raise FixtureMissingError(
            request_key(request), "+".join(self.namespaces), self.llms[0].store.path
        )


def agent_llm(mode: Mode | str | None = None) -> ReplayChain:
    return ReplayChain(AGENT_NAMESPACES, mode)


def judge_llm(mode: Mode | str | None = None) -> ReplayChain:
    return ReplayChain(JUDGE_NAMESPACES, mode)


def preflight(prompt: str, ids: Sequence[str], llm: ReplayChain | None = None) -> list[str]:
    """Cases whose first agent request is not recorded. If the first turn misses, the run misses."""
    llm = llm or agent_llm(Mode.REPLAY)
    return [
        cid
        for cid in ids
        if not llm.has(
            build_request([{"role": "user", "content": rows()[cid]["question"]}], prompt)
        )
    ]


def run_traces(
    prompt: str, ids: Sequence[str], llm: ReplayChain
) -> tuple[dict[str, Trace], list[str]]:
    """Replay (or record) the agent on each case. Returns the traces and the cases that missed.

    A case can pass preflight and still miss at a later turn: if a tool result changed (a KB edit,
    a new probe cache), the second request differs from the recorded one.
    """
    live = llm.mode is not Mode.REPLAY
    spans: list[dict[str, Any]] = []
    missing: list[str] = []
    for i, cid in enumerate(ids):
        tracer = (
            Tracer()
            if live
            else Tracer(
                clock=VirtualClock(VIRTUAL_EPOCH_NS + i * 60_000_000_000),
                ids=SeededIds(f"mediadoctor-lab08:{prompt}:{cid}"),
            )
        )
        try:
            run_agent(
                rows()[cid]["question"], llm=llm, tracer=tracer, case_id=cid, prompt_version=prompt
            )
        except FixtureMissingError:
            missing.append(cid)
            continue
        spans.extend(tracer.span_dicts())
    return lab03.traces_by_case(spans), missing


# --- One suite run ------------------------------------------------------------------------------------


class ReplayMissError(RuntimeError):
    def __init__(self, what: str, missing: Sequence[str]):
        self.missing = list(missing)
        super().__init__(
            f"{len(self.missing)} {what} not recorded (e.g. {', '.join(self.missing[:3])}). The "
            "change alters the requests, so the replayed suite cannot evaluate it. Record them "
            "(EVALS_LLM_MODE=record locally, or the live-evals workflow), review and label the new "
            "outputs, commit the fixtures, and bump the golden manifest."
        )


@dataclass
class SuiteRun:
    """A run of the eval suite: per-case outcomes per metric, plus what it took."""

    label: str
    prompt: str
    fingerprint: str
    outcomes: dict[str, dict[str, dict[str, bool | None]]] = field(default_factory=dict)
    usage: dict[str, Usage] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)  # case id -> full answer (not saved)
    replay_seconds: float = 0.0
    judge_misses: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA,
            "label": self.label,
            "config": {"prompt": self.prompt, "fingerprint": self.fingerprint},
            "golden": {"name": GOLDEN_NAME, "version": GOLDEN_VERSION},
            "tiers": {
                t: {m: dict(sorted(o.items())) for m, o in metrics.items()}
                for t, metrics in self.outcomes.items()
            },
            "usage": {t: u.as_dict() for t, u in self.usage.items()},
            "answers": {cid: text_digest(a) for cid, a in sorted(self.answers.items())},
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SuiteRun:
        if data.get("schema") != RUN_SCHEMA:
            raise ValueError(f"not a {RUN_SCHEMA} file (schema {data.get('schema')!r})")
        return cls(
            data["label"],
            data["config"]["prompt"],
            data["config"]["fingerprint"],
            {t: {m: dict(o) for m, o in ms.items()} for t, ms in data["tiers"].items()},
            {t: Usage.from_dict(u) for t, u in data.get("usage", {}).items()},
        )


def code_outcomes(traces: Mapping[str, Trace], ids: Sequence[str]) -> dict[str, dict[str, bool]]:
    checks = gate_config()["tiers"]["code"]["checks"]
    out: dict[str, dict[str, bool]] = {}
    for name in checks:
        _mode, fn = lab05.CODE_CHECKS[name]
        out[name] = {cid: bool(fn(traces[cid], rows()[cid])) for cid in ids}
    out["all-code-checks"] = {cid: all(out[n][cid] for n in checks) for cid in ids}
    return out


def judge_outcomes(
    items: Mapping[str, Item], ids: Sequence[str], llm: ReplayChain
) -> tuple[dict[str, dict[str, bool | None]], list[str]]:
    """Per judge: PASS/FAIL per case, None where the judge does not apply or could not be parsed."""
    out: dict[str, dict[str, bool | None]] = {}
    misses: list[str] = []
    examples = lab05.items()  # few-shot examples are module 5 train traces
    for name in gate_config()["tiers"]["judges"]["judges"]:
        spec = lab05.load_spec(name)
        res: dict[str, bool | None] = {}
        for cid in ids:
            item = items[cid]
            if not lab05.applies(spec, item):
                res[cid] = None
                continue
            try:
                resp = llm.create(**build_judge_request(spec, item, examples))
            except FixtureMissingError:
                misses.append(f"{name}:{cid}")
                res[cid] = None
                continue
            res[cid] = parse_verdict(cid, text_of(resp)).passed
        out[name] = res
    return out, misses


def run_suite(
    prompt: str | None = None,
    tiers: Sequence[str] = ("code",),
    label: str | None = None,
    mode: Mode | str | None = None,
    release: bool = False,
    holdout_guard: HoldoutGuard | None = None,
) -> SuiteRun:
    """Run the eval tiers for one configuration. Raises ReplayMissError on missing agent fixtures.

    Without `release`, the held-out split is never read (the guard raises if a tier asks for it).
    With `release`, every tier runs on the held-out split instead.
    """
    prompt = prompt or release_prompt()
    if prompt not in AGENT_PROMPTS:
        raise ValueError(f"unknown prompt {prompt!r}; choose from {', '.join(AGENT_PROMPTS)}")
    g = holdout_guard or guard()
    start = time.perf_counter()
    tier_ids = {
        t: g.check(
            holdout_ids() if release else ids_in(tier_splits(t)),
            f"{'release' if release else 'gate'} tier {t}",
            release=release,
        )
        for t in tiers
    }
    all_ids = sorted({cid for ids in tier_ids.values() for cid in ids})
    agent = agent_llm(mode)
    if agent.mode is Mode.REPLAY:
        missing = preflight(prompt, all_ids, agent)
        if missing:
            raise ReplayMissError("agent runs", missing)
    traces, missing = run_traces(prompt, all_ids, agent)
    if missing:
        raise ReplayMissError("agent runs (at a later turn)", missing)
    run = SuiteRun(label or prompt, prompt, fingerprint(prompt))
    items = {cid: lab05.item_from_trace(traces[cid]) for cid in all_ids}
    run.answers = {cid: items[cid].answer for cid in all_ids}
    run.usage["agent"] = agent.usage
    if "code" in tiers:
        run.outcomes["code"] = dict(code_outcomes(traces, tier_ids["code"]))
    if "judges" in tiers:
        jl = judge_llm(mode)
        run.outcomes["judges"], run.judge_misses = judge_outcomes(items, tier_ids["judges"], jl)
        run.usage["judges"] = jl.usage
    run.replay_seconds = time.perf_counter() - start
    return run


# --- Baselines ----------------------------------------------------------------------------------------


@dataclass
class Baseline:
    run: SuiteRun
    source: str  # where it was read from


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError, FileNotFoundError:
        return None


def load_baseline(base_ref: str | None = None) -> Baseline:
    """The baseline committed at `base_ref` (the PR's base); this checkout's if the ref has none."""
    path = rel(baseline_path())
    if base_ref:
        text = git_show(base_ref, path)
        if text is not None:
            try:
                return Baseline(SuiteRun.from_json(json.loads(text)), f"{path} at {base_ref[:12]}")
            except ValueError, KeyError:
                pass  # an older format: fall back to this checkout's baseline
        source = f"{path} in this checkout ({base_ref[:12]} has no usable baseline)"
    else:
        source = f"{path} in this checkout"
    return Baseline(
        SuiteRun.from_json(json.loads(baseline_path().read_text(encoding="utf-8"))), source
    )


def baseline_run() -> SuiteRun:
    return run_suite(release_prompt(), TIERS, label=f"release ({release_prompt()})")


def write_baseline(run: SuiteRun | None = None) -> Path:
    run = run or baseline_run()
    baseline_path().parent.mkdir(parents=True, exist_ok=True)
    baseline_path().write_text(json.dumps(run.to_json(), indent=1) + "\n", encoding="utf-8")
    return baseline_path()


def baseline_problems(head: SuiteRun, base: SuiteRun) -> list[str]:
    """Why the committed baseline does not describe the head run (for a PR, or on main)."""
    problems = []
    if head.fingerprint != base.fingerprint:
        problems.append(
            f"config fingerprint {head.fingerprint} (prompt {head.prompt}) differs from the "
            f"baseline's {base.fingerprint} (prompt {base.prompt})"
        )
    for tier, metrics in head.outcomes.items():
        for m, outcomes in metrics.items():
            if base.outcomes.get(tier, {}).get(m) != outcomes:
                problems.append(f"{tier}/{m}: outcomes differ from the baseline")
    return problems


# --- Comparing two runs -------------------------------------------------------------------------------


def compare(base: SuiteRun, head: SuiteRun, tier: str, rule: GateRule | None = None) -> GateResult:
    metrics = {m: (base.outcomes[tier][m], head.outcomes[tier][m]) for m in head.outcomes[tier]}
    return evaluate_gate(metrics, rule or gate_rule())


def first_line(answer: str, n: int = 90) -> str:
    line = next((ln.strip() for ln in answer.splitlines() if ln.strip()), "")
    return line if len(line) <= n else line[: n - 1] + "…"


def overall(gates: Mapping[str, GateResult]) -> Status:
    order = {Status.PASS: 0, Status.WARN: 1, Status.FAIL: 2}
    return max((g.status for g in gates.values()), key=order.__getitem__, default=Status.PASS)


HEADLINE = {
    Status.PASS: "✅ passed",
    Status.WARN: "⚠️ passed with warnings",
    Status.FAIL: "❌ blocked",
}


def report_markdown(
    base: SuiteRun,
    head: SuiteRun,
    gates: Mapping[str, GateResult],
    base_source: str = "",
    title: str = "Eval gate",
) -> str:
    """The comparison report: posted as the job summary and uploaded as an artifact."""
    status = overall(gates)
    out = [f"## {title}: {HEADLINE[status]}", ""]
    out.append(
        f"**Base:** prompt `{base.prompt}`, fingerprint `{base.fingerprint}`"
        + (f" ({base_source})" if base_source else "")
        + f"  \n**Head:** prompt `{head.prompt}`, fingerprint `{head.fingerprint}`  \n"
        f"**Golden set:** {GOLDEN_NAME} {GOLDEN_VERSION}; replay mode, no API calls; "
        "the held-out split is not used."
    )
    if base.fingerprint == head.fingerprint:
        out.append(
            "\nSame configuration on both sides: any difference would mean the replay is not deterministic."
        )
    for tier, g in gates.items():
        n = max(m.result.n for m in g.metrics)
        names = {"code": "Code checks", "judges": "LLM judges (replayed)"}
        out += ["", f"### {names.get(tier, tier)}: {ICON[g.status]} {g.status.value} (n={n})", ""]
        out.append(g.markdown())
        reasons = describe(g.metrics)
        if reasons:
            out += [""] + [f"- {r}" for r in reasons]
        dropped = [m for m in g.metrics if m.dropped]
        if dropped:
            out.append(
                "\nNot applicable or unparsed on one side (left out of the paired test): "
                + ", ".join(f"{m.metric} {m.dropped}" for m in dropped)
            )
        rows_ = []
        for m in g.metrics:
            if m.metric == "all-code-checks":
                continue
            lost, gained = flips(base.outcomes[tier][m.metric], head.outcomes[tier][m.metric])
            for cid in lost[:8]:
                snippet = first_line(head.answers[cid]) if cid in head.answers else ""
                rows_.append(f"| {m.metric} | {cid} | newly failing | {snippet} |")
            if len(lost) > 8:
                rows_.append(f"| {m.metric} | … | {len(lost) - 8} more newly failing | |")
            if gained:
                rows_.append(
                    f"| {m.metric} | {', '.join(gained[:6])}{' …' if len(gained) > 6 else ''} "
                    f"| newly passing ({len(gained)}) | |"
                )
        if rows_:
            out += ["", "<details><summary>Flips to read first</summary>", ""]
            out += ["| Metric | Case | Change | Head answer (first line) |", "|---|---|---|---|"]
            out += rows_ + ["", "</details>"]
    out += ["", "### Cost and time", ""]
    out += ["| Tier | Run | Calls | Input tokens | Output tokens | Live cost | Recorded latency |"]
    out += ["|---|---|---|---|---|---|---|"]
    for name, run in (("base", base), ("head", head)):
        for kind, u in run.usage.items():
            out.append(
                f"| {kind} | {name} | {u.calls} | {u.input_tokens:,} | {u.output_tokens:,} | "
                f"${u.cost_usd:.2f} | {u.latency_s / 60:.1f} min |"
            )
    if head.replay_seconds:
        b = budget()
        live = sum(head.usage.values(), Usage())
        problems = budget_problems(b, head.replay_seconds, live)
        out.append(
            f"\nReplay took {head.replay_seconds:.1f} s (budget {b.replay_seconds:.0f} s). Re-recording "
            f"the head's tiers live: about ${live.cost_usd:.2f} and "
            f"{live.live_minutes(b.concurrency):.1f} min at {b.concurrency} parallel calls "
            f"(budget ${b.live_usd:.2f}, {b.live_minutes:.0f} min)."
        )
        out += [f"- ❌ over budget: {p}" for p in problems]
    out += [
        "",
        "Rule: block when a metric is worse and McNemar's test (Holm-adjusted within the tier) "
        f"gives p < {gate_rule().alpha}, with a drop of at least {gate_rule().min_effect:.2f}; "
        f"warn when the 95% interval cannot rule out a drop larger than {gate_rule().margin:.2f}.",
    ]
    return "\n".join(out) + "\n"


# --- Hygiene ------------------------------------------------------------------------------------------


def hygiene_review_path() -> Path:
    return repo_root() / "data" / "golden" / "hygiene_review.csv"


def hygiene_review() -> dict[tuple[str, str], str]:
    """Findings someone has read and decided on: {(case id, source): "decision: reason"}."""
    if not hygiene_review_path().exists():
        return {}
    with hygiene_review_path().open(newline="", encoding="utf-8") as fh:
        return {
            (r["case_id"], r["source"]): f"{r['decision']}: {r['reason']}"
            for r in csv.DictReader(fh)
        }


@dataclass
class Hygiene:
    near_duplicates: list[tuple[str, str, float]]
    closest: list[tuple[str, str, float]]
    exact_duplicates: list[tuple[str, str]]
    judge_leaks: list[str]
    contamination: list[tuple[str, str, str]]
    stale: list[str]
    reviewed: dict[tuple[str, str], str] = field(default_factory=dict)

    @property
    def unreviewed_contamination(self) -> list[tuple[str, str, str]]:
        return [c for c in self.contamination if (c[0], c[1]) not in self.reviewed]

    @property
    def problems(self) -> list[str]:
        out = [
            f"near-duplicate across gate and held-out: {a} ~ {b} ({s})"
            for a, b, s in self.near_duplicates
        ]
        out += [f"exact duplicate question: {a} = {b}" for a, b in self.exact_duplicates]
        out += self.judge_leaks
        out += [
            f"contamination (not reviewed): {c} shares '{g}' with {src}"
            for c, src, g in self.unreviewed_contamination
        ]
        out += [f"stale label: {k}" for k in self.stale]
        return out


def contamination_corpus() -> dict[str, str]:
    """Text that a model or a person tuned against: prompts, judge prompts with their examples, the KB."""
    corpus = {f"agent prompt {v}": t for v, t in AGENT_PROMPTS.items()}
    examples = lab05.items()
    for j in gate_config()["tiers"]["judges"]["judges"]:
        spec = lab05.load_spec(j)
        corpus[f"judge {spec.key}"] = "\n".join(
            [spec.criterion, spec.pass_def, spec.fail_def]
            + [
                render_item(examples[e.case_id], spec.context) + "\n" + e.critique
                for e in spec.examples
            ]
        )
    for p in sorted((repo_root() / "data" / "kb").glob("*.md")):
        corpus[f"kb {p.stem}"] = p.read_text(encoding="utf-8")
    return corpus


def label_answers() -> dict[str, str]:
    """{"<prompt>:<case id>": digest of the answer that was labelled}."""
    with label_answers_path().open(newline="", encoding="utf-8") as fh:
        return {f"{r['prompt']}:{r['case_id']}": r["answer_sha"] for r in csv.DictReader(fh)}


def current_answers() -> dict[str, str]:
    """Digests of the answers the recorded runs give now (all labelled cases, both prompts)."""
    out = {}
    for prompt in lab06.PROMPTS:
        for cid, item in lab06.items(prompt, 1).items():
            out[f"{prompt}:{cid}"] = text_digest(item.answer)
    return out


def write_label_answers() -> Path:
    path = label_answers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["prompt", "case_id", "answer_sha"])
        for key, digest in sorted(current_answers().items()):
            w.writerow([*key.split(":", 1), digest])
    return path


def hygiene() -> Hygiene:
    texts = {cid: r["question"] for cid, r in rows().items()}
    side = {cid: ("holdout" if s == HOLDOUT_SPLIT else "gate") for cid, s in split_of().items()}
    closest = cross_split_pairs(texts, side, "gate", "holdout", threshold=0.0)[:3]
    near = [p for p in closest if p[2] >= 0.35]
    seen: dict[str, str] = {}
    exact = []
    for cid, t in sorted(texts.items()):
        key = " ".join(t.lower().split())
        if key in seen:
            exact.append((seen[key], cid))
        seen.setdefault(key, cid)
    sp = split_of()
    leaks = []
    for j in gate_config()["tiers"]["judges"]["judges"]:
        spec = lab05.load_spec(j)
        leaks += [f"judge {spec.key}: {p}" for p in leakage_problems(spec, sp)]
    # Pasted log lines are shared by design (the same clip, the same logcat), so compare the prose.
    eval_cases = {cid: prose(texts[cid]) for cid in ids_in(tier_splits("judges")) + holdout_ids()}
    corpus = {src: prose(t) for src, t in contamination_corpus().items()}
    contamination = ngram_contamination(eval_cases, corpus, n=8)
    stale = stale_labels(label_answers(), current_answers())
    return Hygiene(near, closest, exact, leaks, contamination, stale, hygiene_review())


# --- Release (held-out) ------------------------------------------------------------------------------


def log_holdout_look(run: SuiteRun, note: str = "") -> None:
    path = holdout_log_path()
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(["date", "prompt", "fingerprint", "all_code_checks", "note"])
        rate = pass_rate(list(run.outcomes["code"]["all-code-checks"].values()))
        w.writerow(
            [
                datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                run.prompt,
                run.fingerprint,
                f"{rate:.3f}",
                note,
            ]
        )


def holdout_looks() -> int:
    if not holdout_log_path().exists():
        return 0
    with holdout_log_path().open(newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))


# --- CLI ----------------------------------------------------------------------------------------------


def _tiers(arg: str) -> tuple[str, ...]:
    return TIERS if arg == "all" else (arg,)


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text, end="")


def _append_summary(text: str, path: str | None) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


def cmd_gate(args: argparse.Namespace) -> int:
    tiers = _tiers(args.tier)
    base = load_baseline(args.base_ref)
    try:
        head = run_suite(args.prompt or release_prompt(), tiers, label="head")
    except ReplayMissError as exc:
        text = f"## Eval gate: ⛔ needs re-recorded fixtures\n\n{exc}\n"
        _write(text, args.out)
        _append_summary(text, args.summary)
        print(exc, file=sys.stderr)
        return 3
    gates = {t: compare(base.run, head, t) for t in tiers}
    text = report_markdown(base.run, head, gates, base.source)
    if head.judge_misses:
        text += (
            f"\n⛔ {len(head.judge_misses)} judge calls were not recorded "
            f"(e.g. {', '.join(head.judge_misses[:3])}); re-record them before trusting this tier.\n"
        )
    _write(text, args.out)
    _append_summary(text, args.summary)
    if args.json:
        _write(json.dumps(head.to_json(), indent=1) + "\n", args.json)
    status = overall(gates)
    print(f"eval gate: {status.value}", file=sys.stderr)
    if head.judge_misses:
        return 3
    return 1 if status is Status.FAIL else 0


def cmd_naive(_: argparse.Namespace) -> int:
    base = load_baseline().run
    head = run_suite("v2", ("code",), label="v2")
    print("Release v1 vs candidate v2, code checks on the gate set:\n")
    print(
        f"{'metric':<16} {'v1':>6} {'v2':>6}  {'no-drop':>8}  {'2-pt tol.':>9}  {'5-pt tol.':>9}  paired gate"
    )
    gate = compare(base, head, "code")
    for m in gate.metrics:
        r = m.result
        print(
            f"{m.metric:<16} {r.rate_a:6.3f} {r.rate_b:6.3f}  "
            f"{naive_gate(r.rate_a, r.rate_b).value:>8}  {naive_gate(r.rate_a, r.rate_b, 0.02).value:>9}  "
            f"{naive_gate(r.rate_a, r.rate_b, 0.05).value:>9}  {m.status.value}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mediadoctor-lab08", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight", help="replay misses for a prompt on the gate set")
    p.add_argument("--prompt")
    p = sub.add_parser("run", help="run eval tiers and save the results as JSON")
    p.add_argument("--prompt")
    p.add_argument("--tier", choices=[*TIERS, "all"], default="code")
    p.add_argument("--out")
    p = sub.add_parser("diff", help="a Markdown comparison of two saved runs")
    p.add_argument("base")
    p.add_argument("head")
    p.add_argument("--out")
    p = sub.add_parser("gate", help="run the head and gate it against the base branch's baseline")
    p.add_argument("--base-ref", help="git ref whose evals/baseline.json is the baseline")
    p.add_argument("--tier", choices=[*TIERS, "all"], default="code")
    p.add_argument("--prompt", help="override config/release.toml (experiments)")
    p.add_argument("--summary", help="append the report here (e.g. $GITHUB_STEP_SUMMARY)")
    p.add_argument("--out", help="also write the report to this file")
    p.add_argument("--json", help="write the head run's results to this file")
    p = sub.add_parser("baseline", help="check or rewrite evals/baseline.json")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    p = sub.add_parser("manifest", help="check or rewrite the golden manifest")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    sub.add_parser("hygiene", help="leakage, contamination, and stale labels")
    sub.add_parser("budget", help="replay time and the cost of re-recording each tier")
    p = sub.add_parser("release", help="evaluate on the held-out split (release decisions only)")
    p.add_argument("--prompt")
    p.add_argument(
        "--log", action="store_true", help="append this look to data/golden/holdout_log.csv"
    )
    p.add_argument("--note", default="")
    sub.add_parser("naive", help="fixed thresholds vs the paired gate on v1 -> v2")
    args = ap.parse_args(argv)

    if args.cmd == "preflight":
        prompt = args.prompt or release_prompt()
        ids = ids_in(tier_splits("code"))
        missing = preflight(prompt, ids)
        print(
            f"prompt {prompt} (fingerprint {fingerprint(prompt)}): {len(ids) - len(missing)}/{len(ids)} first requests recorded"
        )
        for cid in missing[:10]:
            print(f"  missing {cid}")
        return 3 if missing else 0
    if args.cmd == "run":
        run = run_suite(args.prompt, _tiers(args.tier))
        text = json.dumps(run.to_json(), indent=1) + "\n"
        _write(text, args.out)
        return 0
    if args.cmd == "diff":
        a = SuiteRun.from_json(json.loads(Path(args.base).read_text(encoding="utf-8")))
        b = SuiteRun.from_json(json.loads(Path(args.head).read_text(encoding="utf-8")))
        gates = {t: compare(a, b, t) for t in b.outcomes if t in a.outcomes}
        _write(report_markdown(a, b, gates, title=f"{a.label} → {b.label}"), args.out)
        return 0
    if args.cmd == "gate":
        return cmd_gate(args)
    if args.cmd == "baseline":
        if args.write:
            print(f"wrote {rel(write_baseline())}")
            return 0
        problems = baseline_problems(baseline_run(), load_baseline().run)
        for p_ in problems:
            print(f"  {p_}")
        print(
            "baseline: "
            + (
                "stale; run `mediadoctor-lab08 baseline --write` and commit it"
                if problems
                else "up to date"
            )
        )
        return 1 if problems else 0
    if args.cmd == "manifest":
        if args.write:
            write_label_answers()
            print(f"wrote {rel(write_manifest(manifest_path(), make_manifest()))}")
            return 0
        problems = manifest_problems()
        m = load_manifest(manifest_path())
        for p_ in problems:
            print(f"  {p_}")
        print(
            f"{m['name']} {m['version']}: "
            + (
                f"{len(problems)} problem(s)"
                if problems
                else f"{len(m['files'])} files and {len(m['splits'])} splits match"
            )
        )
        return 1 if problems else 0
    if args.cmd == "hygiene":
        h = hygiene()
        print("closest gate/held-out pairs (word-trigram Jaccard):")
        for a, b, s in h.closest:
            print(f"  {a} ~ {b}: {s:.3f}")
        print(
            f"near-duplicates (>= 0.35): {len(h.near_duplicates)}; exact duplicates: {len(h.exact_duplicates)}"
        )
        print(
            f"judge example leaks: {len(h.judge_leaks)}; 8-gram contamination: "
            f"{len(h.contamination)} ({len(h.contamination) - len(h.unreviewed_contamination)} reviewed); "
            f"stale labels: {len(h.stale)}"
        )
        for c, src, g in h.contamination:
            if (c, src) in h.reviewed:
                print(f"  reviewed: {c} shares '{g}' with {src} -> {h.reviewed[(c, src)]}")
        for p_ in h.problems:
            print(f"  {p_}")
        return 1 if h.problems else 0
    if args.cmd == "budget":
        b = budget()
        for tier in TIERS:
            run = run_suite(None, (tier,))
            live = sum(run.usage.values(), Usage())
            print(
                f"{tier:<7} replay {run.replay_seconds:5.2f} s | live re-record: {live.calls} calls, "
                f"{live.input_tokens:,} in / {live.output_tokens:,} out tokens, ${live.cost_usd:.2f}, "
                f"{live.live_minutes(b.concurrency):.1f} min at {b.concurrency} parallel"
            )
            for p_ in budget_problems(b, run.replay_seconds, live):
                print(f"  over budget: {p_}")
        return 0
    if args.cmd == "release":
        run = run_suite(args.prompt, ("code",), release=True)
        n = len(run.outcomes["code"]["all-code-checks"])
        for m, o in run.outcomes["code"].items():
            print(f"{m:<16} {pass_rate(list(o.values())):.3f}  (n={n}, held-out)")
        if args.log:
            log_holdout_look(run, args.note)
        print(f"held-out looks logged so far: {holdout_looks()}")
        return 0
    if args.cmd == "naive":
        return cmd_naive(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
