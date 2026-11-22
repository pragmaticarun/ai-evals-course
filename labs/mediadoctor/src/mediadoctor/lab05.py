"""Module 5 lab: code checks and LLM judges for MediaDoctor, validated against human labels.

    uv run mediadoctor-lab05 labels                     # the labelled trace set, by split
    uv run mediadoctor-lab05 checks                     # code checks vs human labels
    uv run mediadoctor-lab05 judge tool-grounding --version v1 --split dev
    uv run mediadoctor-lab05 disagreements tool-grounding --version v1 --split dev
    uv run mediadoctor-lab05 validate --split dev       # every final judge on dev
    uv run mediadoctor-lab05 validate --split test      # once, at the end
    uv run mediadoctor-lab05 estimate                   # corrected pass rate with a bootstrap CI
    uv run mediadoctor-lab05 likert                     # a 1-5 judge against the binary one
    uv run mediadoctor-lab05 leaks                      # leakage checks on every judge spec

Replay mode (default) needs no API key. The agent traces, the judge outputs, and the human labels
are synthetic-authored (see scripts/author_module05_fixtures.py).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import LLM, Mode, Tracer, repo_root, text_of
from evalkit.annotate import Annotation, load_annotations
from evalkit.judge import (
    Confusion,
    Item,
    JudgeSpec,
    Verdict,
    bootstrap_corrected,
    confusion,
    disagreements,
    leakage_problems,
    load_judge,
    run_judge,
)
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from evalkit.viewer import root_of
from mediadoctor import lab03, lab04
from mediadoctor.lab01 import CITE_RE, has_format
from mediadoctor.lab02 import TOOL_CITE_RE
from mediadoctor.toolagent import run_agent

AGENT_NAMESPACE = "mediadoctor-m5"
JUDGE_NAMESPACE = "mediadoctor-judges"
FINAL = {"tool-grounding": "v2", "false-premise": "v1", "next-step": "v1"}
VERSIONS = {"tool-grounding": ("v1", "v2"), "false-premise": ("v1",), "next-step": ("v1",)}
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 5

Trace = list[dict[str, Any]]


def judges_dir() -> Path:
    return repo_root() / "config" / "judges"


def labels_path() -> Path:
    return repo_root() / "data" / "labels" / "module05_reference.csv"


def spec_path(name: str, version: str) -> Path:
    return judges_dir() / f"{name}.{version}.toml"


def load_spec(name: str, version: str | None = None) -> JudgeSpec:
    return load_judge(spec_path(name, version or FINAL[name]))


# --- The labelled trace set -------------------------------------------------------------------------


def label_rows() -> list[dict[str, Any]]:
    """Every dataset v1 query (all splits) that matches a module 3 scenario: 137 queries."""
    return [r for r in lab04.load_dataset() if lab04.scenario_for(r)]


def splits() -> dict[str, str]:
    return {r["id"]: r["split"] for r in lab04.load_dataset()}


def run_traces(llm: LLM | None = None) -> list[dict[str, Any]]:
    llm = llm or LLM(namespace=AGENT_NAMESPACE)
    live = llm.mode is not Mode.REPLAY
    spans: list[dict[str, Any]] = []
    for i, r in enumerate(label_rows()):
        tracer = (
            Tracer()
            if live
            else Tracer(
                clock=VirtualClock(VIRTUAL_EPOCH_NS + i * 60_000_000_000),
                ids=SeededIds(f"mediadoctor-lab05:{r['id']}"),
            )
        )
        run_agent(r["question"], llm=llm, tracer=tracer, case_id=r["id"])
        spans.extend(tracer.span_dicts())
    return spans


@cache
def traces() -> dict[str, Trace]:
    """The module 5 traces, replayed (cached: they never change within a process)."""
    return lab03.traces_by_case(run_traces())


def item_from_trace(trace: Trace) -> Item:
    a = root_of(trace)["attributes"]
    tools = tuple(
        (
            s["attributes"]["gen_ai.tool.name"],
            s["attributes"].get("gen_ai.tool.call.arguments", ""),
            str(s["attributes"].get("gen_ai.tool.call.result", "")),
            s["status"]["code"] != "ERROR",
        )
        for s in lab03.ordered_spans(trace)
        if s["attributes"].get("gen_ai.operation.name") == "execute_tool"
    )
    return Item(
        str(a.get("mediadoctor.case.id")),
        str(a.get("mediadoctor.question", "")),
        str(a.get("mediadoctor.answer", "")),
        tools,
    )


@cache
def items() -> dict[str, Item]:
    return {cid: item_from_trace(t) for cid, t in traces().items()}


def annotations(path: Path | str | None = None) -> dict[str, Annotation]:
    return {a.case_id: a for a in load_annotations(path or labels_path())}


def human_pass(
    mode: str, ids: list[str], labels: dict[str, Annotation] | None = None
) -> dict[str, bool]:
    """Per-criterion human label: PASS unless the trace was tagged with this failure mode."""
    labels = labels or annotations()
    return {cid: mode not in labels[cid].modes for cid in ids}


def applies(spec: JudgeSpec, item: Item) -> bool:
    """Run a judge only where its criterion can be judged."""
    if spec.name == "tool-grounding":
        return any(ok for _, _, _, ok in item.tools)  # nothing to contradict without tool output
    return True


def ids_in(split: str) -> list[str]:
    sp = splits()
    return [cid for cid in items() if sp.get(cid) == split]


# --- Code checks ------------------------------------------------------------------------------------


def check_format(trace: Trace) -> bool:
    return has_format({}, item_from_trace(trace).answer)


def check_citations(trace: Trace) -> bool:
    """Every [tool:x] cited was called successfully; any [kb:y] cited was actually retrieved."""
    it = item_from_trace(trace)
    ok_tools = {name for name, _, _, ok in it.tools if ok}
    retrieved = {
        d for s in trace for d in s["attributes"].get("mediadoctor.retrieval.doc_ids", []) or []
    }
    return all(t in ok_tools for t in TOOL_CITE_RE.findall(it.answer)) and all(
        d in retrieved for d in CITE_RE.findall(it.answer)
    )


ASKS = re.compile(r"\bsend (the|us|me)\b|\bwhich (device|file|clip)\b", re.I)


def check_investigated(trace: Trace, row: dict[str, Any]) -> bool:
    """If the question gives something to inspect, an inspecting tool ran, or the agent asked for it."""
    it = item_from_trace(trace)
    needed = [t for t in row["expected_tools"] if t != "search_kb"]
    if not needed:
        return True
    return any(name in needed for name, _, _, _ in it.tools) or bool(ASKS.search(it.answer))


CODE_CHECKS = {
    "format": ("format-violation", lambda tr, row: check_format(tr)),
    "citations": ("fabricated-evidence", lambda tr, row: check_citations(tr)),
    "investigated": ("skipped-investigation", check_investigated),
}


def code_check_results(
    split: str | None = None,
) -> dict[str, tuple[dict[str, bool], dict[str, bool]]]:
    """{check: (human per-mode labels, check verdicts)} on the given split (all splits if None)."""
    rows = {r["id"]: r for r in label_rows()}
    ids = [cid for cid in items() if split is None or rows[cid]["split"] == split]
    out = {}
    for name, (mode, fn) in CODE_CHECKS.items():
        verdicts = {cid: bool(fn(traces()[cid], rows[cid])) for cid in ids}
        out[name] = (human_pass(mode, ids), verdicts)
    return out


# --- Judges -------------------------------------------------------------------------------------------


def judge_llm() -> LLM:
    return LLM(namespace=JUDGE_NAMESPACE)


def run_spec(
    spec: JudgeSpec, ids: list[str], pool: dict[str, Item] | None = None, llm: LLM | None = None
) -> dict[str, Verdict]:
    pool = pool or items()
    llm = llm or judge_llm()
    todo = [pool[cid] for cid in ids if applies(spec, pool[cid])]
    return run_judge(llm.create, spec, todo, items(), text_of)


@dataclass(frozen=True)
class Validation:
    spec: JudgeSpec
    split: str
    result: Confusion
    verdicts: dict[str, Verdict]
    human: dict[str, bool]


def validate(name: str, version: str | None, split: str, llm: LLM | None = None) -> Validation:
    spec = load_spec(name, version)
    if split == "train":
        raise ValueError("few-shot examples come from train; validate on dev, and on test once")
    verdicts = run_spec(spec, ids_in(split), llm=llm)
    human = human_pass(spec.mode, list(verdicts))
    return Validation(
        spec, split, confusion(human, {k: v.passed for k, v in verdicts.items()}), verdicts, human
    )


# --- Corrected estimate on unlabelled traffic ---------------------------------------------------------


@cache
def m3_items() -> dict[str, Item]:
    """Module 3's 100 traces, used here as traffic the judge has not been validated on."""
    return {cid: item_from_trace(t) for cid, t in lab03.traces_by_case(lab03.run_cases()).items()}


def estimate(name: str = "tool-grounding", llm: LLM | None = None):
    """Judge the module 3 traces, then correct the raw pass rate with test-split TPR and TNR."""
    spec = load_spec(name)
    pool = m3_items()
    unl = run_spec(spec, list(pool), pool=pool, llm=llm)
    test = validate(name, None, "test", llm=llm)
    labelled = [(test.human[c], bool(v.passed)) for c, v in test.verdicts.items()]
    est = bootstrap_corrected(
        labelled, [bool(v.passed) for v in unl.values()], draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED
    )
    m3_ref = {a.case_id: a for a in load_annotations(lab03.reference_labels_path())}
    truth = sum(spec.mode not in m3_ref[c].modes for c in unl) / len(unl)
    return est, truth, test.result


# --- A 1-5 judge, for comparison ---------------------------------------------------------------------

LIKERT_SYSTEM = """\
You evaluate answers from MediaDoctor, an assistant for Android and multimedia engineers.
Rate how actionable the answer's "Next step" is, from 1 (no usable next step) to 5 (a concrete,
specific action the engineer can take right away). Respond with JSON only:
{"critique": "<one or two sentences>", "score": 1-5}"""


def likert_request(item: Item) -> dict[str, Any]:
    from evalkit.config import load_models

    role = load_models()["judge"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": LIKERT_SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": f"<question>\n{item.question}\n</question>\n<answer>\n{item.answer}\n</answer>",
            }
        ],
    }


def likert_scores(split: str, llm: LLM | None = None) -> dict[str, int]:
    llm = llm or judge_llm()
    out = {}
    for cid in ids_in(split):
        text = text_of(llm.create(**likert_request(items()[cid])))
        out[cid] = int(json.loads(re.search(r"\{.*\}", text, re.S).group(0))["score"])
    return out


# --- CLI ----------------------------------------------------------------------------------------------


def _print_validation(v: Validation, show_disagreements: bool = False) -> None:
    print(f"{v.spec.key:<22} {v.split:<5} {v.result}")
    if show_disagreements:
        for cid, kind in disagreements(v.human, {k: x.passed for k, x in v.verdicts.items()}):
            print(f"  {cid}  {kind}: {v.verdicts[cid].critique}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mediadoctor-lab05", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("labels", help="the labelled trace set by split")
    c = sub.add_parser("checks", help="code checks against human labels")
    c.add_argument("--split")
    for name in ("judge", "disagreements"):
        j = sub.add_parser(name, help=f"{name} for one judge on one split")
        j.add_argument("judge", choices=sorted(FINAL))
        j.add_argument("--version")
        j.add_argument("--split", default="dev")
    v = sub.add_parser("validate", help="every final judge on one split")
    v.add_argument("--split", default="dev")
    sub.add_parser(
        "estimate", help="corrected pass rate on the module 3 traces, with a bootstrap CI"
    )
    lk = sub.add_parser(
        "likert", help="a 1-5 actionability judge against the binary next-step judge"
    )
    lk.add_argument("--split", default="dev")
    sub.add_parser("leaks", help="leakage checks on every judge spec")
    sub.add_parser("show", help="print a judge's full prompt for one trace").add_argument("judge")
    args = p.parse_args(argv)

    if args.cmd == "labels":
        labels = annotations()
        sp = splits()
        by = Counter((sp[c], a.verdict) for c, a in labels.items())
        modes = Counter((sp[c], m) for c, a in labels.items() for m in a.modes)
        for s in ("train", "dev", "test"):
            n = by[(s, "pass")] + by[(s, "fail")]
            ms = ", ".join(f"{m} {k}" for (ss, m), k in sorted(modes.items()) if ss == s)
            print(f"{s:<5} {n:>3} traces, {by[(s, 'fail')]:>2} failing   {ms}")
        return 0
    if args.cmd == "checks":
        for name, (human, verdict) in code_check_results(args.split).items():
            print(f"{name:<13} ({CODE_CHECKS[name][0]:<21}) {confusion(human, verdict)}")
        return 0
    if args.cmd in ("judge", "disagreements"):
        res = validate(args.judge, args.version, args.split)
        _print_validation(res, show_disagreements=args.cmd == "disagreements")
        return 0
    if args.cmd == "validate":
        for name in FINAL:
            _print_validation(validate(name, None, args.split))
        return 0
    if args.cmd == "estimate":
        est, truth, test = estimate()
        print(f"judge {load_spec('tool-grounding').key} on test: {test}")
        print(est)
        print(f"true pass rate from the module 3 reference labels: {truth:.3f}")
        return 0
    if args.cmd == "likert":
        scores = likert_scores(args.split)
        human = human_pass("vague-next-step", list(scores))
        print("score  human PASS  human FAIL")
        for s in range(1, 6):
            hp = sum(1 for c, x in scores.items() if x == s and human[c])
            hf = sum(1 for c, x in scores.items() if x == s and not human[c])
            print(f"{s:>5}  {hp:>10}  {hf:>10}")
        for t in (3, 4, 5):
            print(
                f"PASS if score >= {t}: {confusion(human, {c: x >= t for c, x in scores.items()})}"
            )
        binary = validate("next-step", None, args.split)
        print(f"binary next-step judge:  {binary.result}")
        return 0
    if args.cmd == "leaks":
        sp = splits()
        bad = 0
        for name, versions in VERSIONS.items():
            for ver in versions:
                probs = leakage_problems(load_spec(name, ver), sp)
                bad += len(probs)
                print(f"{name}@{ver}: {'ok' if not probs else '; '.join(probs)}")
        return 1 if bad else 0
    if args.cmd == "show":
        from evalkit.judge import build_judge_request

        spec = load_spec(args.judge)
        cid = next(c for c in ids_in("dev") if applies(spec, items()[c]))
        req = build_judge_request(spec, items()[cid], items())
        print(req["system"])
        print("\n--- user message ---")
        print(req["messages"][0]["content"])
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
