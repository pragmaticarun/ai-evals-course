"""Module 2 lab: run the tool-using agent with tracing, export JSONL, and check traces.

    uv run mediadoctor-lab02 run --out runs/m2_traces.jsonl     # all 8 cases, replay mode
    uv run mediadoctor-lab02 run --case m2q03                    # one case
    uv run evalkit view runs/m2_traces.jsonl m2q03               # tree view of one trace
    uv run mediadoctor-lab02 probe                               # refresh the ffprobe cache (needs ffprobe)

Replay mode (default) needs no API key: model responses come from fixtures/recorded/ and the
trace clock is virtual, so trace IDs, timings, tokens, and costs are identical on every run.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evalkit import LLM, Mode, Tracer, repo_root
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from evalkit.viewer import group_traces, render_table, root_of
from mediadoctor.lab01 import has_format
from mediadoctor.toolagent import AGENT_TOOLS_NAMESPACE, run_agent
from mediadoctor.tools import refresh_probe_cache

TOOL_CITE_RE = re.compile(r"\[tool:([a-z_]+)\]")
STEP_BUDGET = 4  # model calls per question


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or repo_root() / "data" / "datasets" / "module02_cases.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def make_tracer(case_id: str, index: int, live: bool) -> Tracer:
    if live:
        return Tracer()  # wall clock and random ids
    # One minute apart on the virtual clock, ids seeded by case id: stable across runs.
    clock = VirtualClock(VIRTUAL_EPOCH_NS + index * 60_000_000_000)
    return Tracer(clock=clock, ids=SeededIds(f"mediadoctor-lab02:{case_id}"))


def run_cases(case_ids: list[str] | None = None, llm: LLM | None = None) -> list[dict[str, Any]]:
    """Run the agent on the selected cases; return all spans as dicts (JSONL rows)."""
    llm = llm or LLM(namespace=AGENT_TOOLS_NAMESPACE)
    live = llm.mode is not Mode.REPLAY
    spans: list[dict[str, Any]] = []
    for i, case in enumerate(load_cases()):
        if case_ids and case["id"] not in case_ids:
            continue
        tracer = make_tracer(case["id"], i, live)
        run_agent(case["question"], llm=llm, tracer=tracer, case_id=case["id"])
        spans.extend(tracer.span_dicts())
    return spans


# --- Trace-level checks -------------------------------------------------------------------------
# Module 1's checks looked only at the final answer. These look at what the agent actually did.

Trace = list[dict[str, Any]]


def _answer(trace: Trace) -> str:
    return str(root_of(trace)["attributes"].get("mediadoctor.answer", ""))


def _tool_spans(trace: Trace) -> list[dict[str, Any]]:
    return [s for s in trace if s["attributes"].get("gen_ai.operation.name") == "execute_tool"]


def check_format(trace: Trace) -> bool:
    return has_format({}, _answer(trace))


def check_evidence_is_real(trace: Trace) -> bool:
    """Every [tool:X] the answer cites must match a SUCCESSFUL execute_tool span for X."""
    ok_tools = {
        s["attributes"]["gen_ai.tool.name"]
        for s in _tool_spans(trace)
        if s["status"]["code"] != "ERROR"
    }
    return all(t in ok_tools for t in TOOL_CITE_RE.findall(_answer(trace)))


def check_no_repeat_retrieval(trace: Trace) -> bool:
    """No two retrievals in one run may return the same documents (wasted calls)."""
    seen = []
    for s in trace:
        if s["attributes"].get("gen_ai.operation.name") == "retrieval":
            ids = tuple(s["attributes"].get("mediadoctor.retrieval.doc_ids", []))
            if ids in seen:
                return False
            seen.append(ids)
    return True


def check_step_budget(trace: Trace) -> bool:
    calls = [s for s in trace if s["attributes"].get("gen_ai.operation.name") == "chat"]
    return len(calls) <= STEP_BUDGET


TRACE_CHECKS: dict[str, Callable[[Trace], bool]] = {
    "format": check_format,
    "evidence_is_real": check_evidence_is_real,
    "no_repeat_retrieval": check_no_repeat_retrieval,
    "step_budget": check_step_budget,
}


def check_traces(spans: list[dict[str, Any]]) -> dict[str, dict[str, bool]]:
    """{case_id: {check_name: passed}}"""
    out = {}
    for trace in group_traces(spans).values():
        cid = str(root_of(trace)["attributes"].get("mediadoctor.case.id"))
        out[cid] = {name: fn(trace) for name, fn in TRACE_CHECKS.items()}
    return dict(sorted(out.items()))


def render_checks(results: dict[str, dict[str, bool]]) -> str:
    names = list(TRACE_CHECKS)
    lines = ["case    " + "  ".join(f"{n:<19}" for n in names)]
    for cid, res in results.items():
        lines.append(f"{cid:<7} " + "  ".join(f"{'pass' if res[n] else 'FAIL':<19}" for n in names))
    totals = "  ".join(
        f"{sum(r[n] for r in results.values())}/{len(results)}".ljust(19) for n in names
    )
    lines.append(f"{'total':<7} {totals}")
    return "\n".join(lines)


# --- CLI ----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mediadoctor-lab02", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="run cases, print trace summary and trace checks")
    p_run.add_argument("--case", action="append", help="case id (repeatable); default all")
    p_run.add_argument("--out", help="write spans as JSONL, e.g. runs/m2_traces.jsonl")
    sub.add_parser("probe", help="refresh data/media/probes.json with the real ffprobe")
    args = parser.parse_args(argv)

    if args.cmd == "probe":
        print(f"wrote {refresh_probe_cache()}")
        return 0
    spans = run_cases(args.case)
    print(render_table(spans))
    print()
    print(render_checks(check_traces(spans)))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for s in spans:
                fh.write(json.dumps(s, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(spans)} spans to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
