"""Module 3 lab: error analysis on 100 MediaDoctor traces (replay mode, no API key).

    uv run mediadoctor-lab03 run --out runs/m3_traces.jsonl      # replay the 100-trace set
    uv run mediadoctor-lab03 review m3t004                       # read one trace, review layout
    uv run mediadoctor-lab03 annotate --labels runs/m3_labels.csv  # open coding, resumable
    uv run mediadoctor-lab03 notes --labels runs/m3_labels.csv     # all failure notes, for axial coding
    uv run mediadoctor-lab03 code --labels runs/m3_labels.csv --modes runs/m3_modes.toml
    uv run mediadoctor-lab03 rank --labels runs/m3_labels.csv --modes runs/m3_modes.toml \
        --taxonomy runs/taxonomy.csv --svg runs/pareto.svg
    uv run mediadoctor-lab03 saturation --labels runs/m3_labels.csv
    uv run mediadoctor-lab03 errors | retrieval | signals         # focused analyses
    uv run mediadoctor-lab03 compare --labels runs/m3_labels.csv  # against the reference labels

Without --labels/--modes, commands use the course's reference annotations (synthetic-authored).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from evalkit import LLM, Mode, Tracer, repo_root
from evalkit.annotate import (
    Annotation,
    compare_verdicts,
    first_upstream_counts,
    load_annotations,
    load_modes,
    mode_overlap,
    pareto_svg,
    pareto_text,
    rank_modes,
    render_ranked,
    render_saturation,
    saturation_curve,
    save_annotations,
    uncoded,
    upsert_annotation,
    write_taxonomy_csv,
)
from evalkit.trace import VIRTUAL_EPOCH_NS, SeededIds, VirtualClock
from evalkit.viewer import group_traces, root_of
from mediadoctor.lab01 import has_format
from mediadoctor.lab02 import STEP_BUDGET, check_evidence_is_real, check_no_repeat_retrieval
from mediadoctor.toolagent import run_agent

NAMESPACE = "mediadoctor-m3"
Trace = list[dict[str, Any]]
TOOL_CITE_RE = re.compile(r"\[tool:([a-z_]+)\]")


def cases_path() -> Path:
    return repo_root() / "data" / "datasets" / "module03_cases.jsonl"


def reference_labels_path() -> Path:
    return repo_root() / "data" / "labels" / "module03_reference.csv"


def reference_modes_path() -> Path:
    return repo_root() / "data" / "labels" / "module03_modes.toml"


def load_cases(path: Path | str | None = None) -> list[dict[str, Any]]:
    with Path(path or cases_path()).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def make_tracer(case_id: str, index: int, live: bool) -> Tracer:
    if live:
        return Tracer()
    clock = VirtualClock(VIRTUAL_EPOCH_NS + index * 60_000_000_000)
    return Tracer(clock=clock, ids=SeededIds(f"mediadoctor-lab03:{case_id}"))


def run_cases(case_ids: list[str] | None = None, llm: LLM | None = None) -> list[dict[str, Any]]:
    llm = llm or LLM(namespace=NAMESPACE)
    live = llm.mode is not Mode.REPLAY
    spans: list[dict[str, Any]] = []
    for i, case in enumerate(load_cases()):
        if case_ids and case["id"] not in case_ids:
            continue
        tracer = make_tracer(case["id"], i, live)
        run_agent(case["question"], llm=llm, tracer=tracer, case_id=case["id"])
        spans.extend(tracer.span_dicts())
    return spans


def traces_by_case(spans: list[dict[str, Any]]) -> dict[str, Trace]:
    out = {}
    for trace in group_traces(spans).values():
        out[str(root_of(trace)["attributes"].get("mediadoctor.case.id"))] = trace
    return dict(sorted(out.items()))


def load_traces(path: str | None) -> dict[str, Trace]:
    if path:
        with open(path, encoding="utf-8") as fh:
            return traces_by_case([json.loads(line) for line in fh if line.strip()])
    return traces_by_case(run_cases())


# --- Reading a trace for review ----------------------------------------------------------------


def _op(span: dict[str, Any]) -> str:
    return str(span["attributes"].get("gen_ai.operation.name", ""))


def ordered_spans(trace: Trace) -> list[dict[str, Any]]:
    """Spans in execution order (start time, then depth) without the root."""
    return sorted(
        (s for s in trace if s["parent_span_id"]),
        key=lambda s: (s["start_time_unix_nano"], s["name"]),
    )


def category(span: dict[str, Any]) -> str:
    """The step label used in the first_upstream column."""
    op = _op(span)
    if op == "chat":
        reasons = span["attributes"].get("gen_ai.response.finish_reasons", [])
        return "chat:plan" if "tool_use" in reasons else "chat:answer"
    if op == "execute_tool":
        return f"execute_tool {span['attributes'].get('gen_ai.tool.name')}"
    return op or span["name"]


def _short(text: Any, n: int = 150) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def render_review(trace: Trace, width: int = 150) -> str:
    """A compact, numbered view designed for annotation: question, each step, answer."""
    root = root_of(trace)
    a = root["attributes"]
    lines = [
        f"case {a.get('mediadoctor.case.id')}   trace {root['trace_id'][:12]}   "
        f"{a.get('mediadoctor.steps')} model calls   ${a.get('evalkit.cost.usd', 0):.4f}",
        f"Q: {a.get('mediadoctor.question')}",
        "",
    ]
    for i, s in enumerate(ordered_spans(trace), 1):
        sa = s["attributes"]
        err = "  ERROR" if s["status"]["code"] == "ERROR" else ""
        cat = category(s)
        if _op(s) == "chat":
            detail = f"in={sa.get('gen_ai.usage.input_tokens')} out={sa.get('gen_ai.usage.output_tokens')}"
        elif _op(s) == "execute_tool":
            detail = f"args={sa.get('gen_ai.tool.call.arguments')}  ->  {_short(sa.get('gen_ai.tool.call.result', ''), width)}"
        else:
            detail = f"query={sa.get('gen_ai.retrieval.query.text')!r} k={sa.get('gen_ai.retrieval.top_k')} -> {sa.get('mediadoctor.retrieval.doc_ids')}"
        lines.append(f"  [{i}] {cat:<24}{err}  {detail}")
    lines += [
        "",
        "Answer:",
        *("  " + ln for ln in str(a.get("mediadoctor.answer", "")).splitlines()),
    ]
    return "\n".join(lines)


# --- Automatic signals: where to look first (not labels) ------------------------------------


def _tool_spans(trace: Trace) -> list[dict[str, Any]]:
    return sorted(
        (s for s in trace if _op(s) == "execute_tool"), key=lambda s: s["start_time_unix_nano"]
    )


def signals(trace: Trace, case: dict[str, Any]) -> list[str]:
    """Cheap, automatic flags that help you choose what to read. They are not failure labels:
    a flagged trace can be fine (a recovered tool error) and an unflagged one can be wrong."""
    out = []
    tools = _tool_spans(trace)
    answer = str(root_of(trace)["attributes"].get("mediadoctor.answer", ""))
    errors = [s for s in tools if s["status"]["code"] == "ERROR"]
    if errors:
        out.append("tool_error")
        ok_names = {
            s["attributes"]["gen_ai.tool.name"] for s in tools if s["status"]["code"] != "ERROR"
        }
        if any(e["attributes"]["gen_ai.tool.name"] not in ok_names for e in errors):
            out.append("unrecovered_tool_error")
    if not check_evidence_is_real(trace) or any(
        t not in {s["attributes"]["gen_ai.tool.name"] for s in tools}
        for t in TOOL_CITE_RE.findall(answer)
    ):
        out.append("cites_missing_evidence")
    if case.get("expected_tools") and not tools:
        out.append("no_tool_calls")
    if not check_no_repeat_retrieval(trace):
        out.append("repeat_retrieval")
    if sum(_op(s) == "chat" for s in trace) > STEP_BUDGET:
        out.append("over_step_budget")
    retrieved = [s for s in trace if _op(s) == "retrieval"]
    if retrieved and case.get("expected_kb"):
        got = {
            d for s in retrieved for d in s["attributes"].get("mediadoctor.retrieval.doc_ids", [])
        }
        if not set(case["expected_kb"]) & got:
            out.append("retrieval_miss")
    if not has_format({}, answer):
        out.append("format")
    return out


def signal_table(
    traces: dict[str, Trace], cases: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    return {cid: signals(t, cases[cid]) for cid, t in traces.items()}


# --- Focused analyses ---------------------------------------------------------------------------


def tool_error_report(traces: dict[str, Trace]) -> list[dict[str, str]]:
    """Every failed tool call, and what the agent did next: retried successfully, gave up, or
    cited the tool anyway (the compounding case)."""
    rows = []
    for cid, trace in traces.items():
        tools = _tool_spans(trace)
        answer = str(root_of(trace)["attributes"].get("mediadoctor.answer", ""))
        cited = set(TOOL_CITE_RE.findall(answer))
        for i, s in enumerate(tools):
            if s["status"]["code"] != "ERROR":
                continue
            name = s["attributes"]["gen_ai.tool.name"]
            retried_ok = any(
                t["attributes"]["gen_ai.tool.name"] == name and t["status"]["code"] != "ERROR"
                for t in tools[i + 1 :]
            )
            if retried_ok:
                outcome = "recovered"
            elif name in cited:
                outcome = "cited anyway"
            else:
                outcome = "gave up"
            msg = str(s["status"].get("message", ""))
            rows.append(
                {
                    "case_id": cid,
                    "tool": name,
                    "arguments": str(s["attributes"].get("gen_ai.tool.call.arguments")),
                    "error": msg.split(". Available")[0],
                    "outcome": outcome,
                }
            )
    return rows


def retrieval_report(
    traces: dict[str, Trace], cases: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One row per retrieval span on cases that name the document they need."""
    rows = []
    for cid, trace in traces.items():
        exp = cases[cid].get("expected_kb") or []
        if not exp:
            continue
        for s in sorted(
            (s for s in trace if _op(s) == "retrieval"), key=lambda s: s["start_time_unix_nano"]
        ):
            a = s["attributes"]
            got = list(a.get("mediadoctor.retrieval.doc_ids", []))
            rows.append(
                {
                    "case_id": cid,
                    "query": a.get("gen_ai.retrieval.query.text"),
                    "k": a.get("gen_ai.retrieval.top_k"),
                    "returned": got,
                    "expected": exp,
                    "hit": bool(set(exp) & set(got)),
                }
            )
    return rows


# --- Interactive annotation -------------------------------------------------------------------

InputFn = Callable[[str], str]
PrintFn = Callable[..., None]


def annotate_session(
    traces: dict[str, Trace],
    labels_path: Path | str,
    annotator: str = "",
    input_fn: InputFn = input,
    print_fn: PrintFn = print,
    redo: bool = False,
) -> int:
    """Open coding: for each trace, pass/fail, a free-text note, and the first upstream failure.
    Writes after every trace, so you can stop (q) and resume later. Returns traces labelled."""
    done = {a.case_id for a in load_annotations(labels_path)}
    queue = [cid for cid in traces if redo or cid not in done]
    labelled, i = 0, 0
    while i < len(queue):
        cid = queue[i]
        trace = traces[cid]
        print_fn(f"\n=== {i + 1}/{len(queue)} to go · {len(done)} labelled so far ===")
        print_fn(render_review(trace))
        spans = ordered_spans(trace)
        choice = input_fn("\n[p]ass  [f]ail  [s]kip  [b]ack  [q]uit > ").strip().lower()
        if choice == "q":
            break
        if choice == "s":
            i += 1
            continue
        if choice == "b":
            i = max(0, i - 1)
            continue
        if choice not in ("p", "f"):
            print_fn("please answer p, f, s, b or q")
            continue
        ann = Annotation(
            case_id=cid,
            verdict="pass" if choice == "p" else "fail",
            annotator=annotator,
            trace_id=root_of(trace)["trace_id"],
            annotated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        if choice == "f":
            ann.note = input_fn("note: what went wrong, in your own words > ").strip()
            raw = input_fn(
                f"first upstream failure: step number 1-{len(spans)} (Enter = not sure) > "
            ).strip()
            if raw.isdigit() and 1 <= int(raw) <= len(spans):
                ann.first_upstream = category(spans[int(raw) - 1])
            codes = input_fn("failure modes, comma separated (Enter = code later) > ").strip()
            ann.modes = [m.strip() for m in codes.split(",") if m.strip()]
        else:
            ann.note = input_fn("note (optional) > ").strip()
        upsert_annotation(labels_path, ann)
        done.add(cid)
        labelled += 1
        i += 1
    return labelled


def code_session(
    labels_path: Path | str,
    known_modes: list[str],
    input_fn: InputFn = input,
    print_fn: PrintFn = print,
) -> int:
    """Axial coding pass: show each failing note without modes and ask for mode ids."""
    anns = load_annotations(labels_path)
    todo = uncoded(anns)
    print_fn(
        f"{len(todo)} failing traces to code. Known modes: {', '.join(known_modes) or '(none yet)'}"
    )
    n = 0
    for a in todo:
        print_fn(f"\n{a.case_id} [{a.first_upstream or '?'}] {a.note}")
        raw = input_fn("modes (comma separated, Enter = skip, q = stop) > ").strip()
        if raw.lower() == "q":
            break
        if raw:
            a.modes = [m.strip() for m in raw.split(",") if m.strip()]
            n += 1
    save_annotations(labels_path, anns)
    return n


# --- CLI ----------------------------------------------------------------------------------------


def _labels(args: argparse.Namespace) -> list[Annotation]:
    return load_annotations(args.labels or reference_labels_path())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mediadoctor-lab03", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="replay all 100 traces; print counts; optionally write JSONL")
    r.add_argument("--out")
    v = sub.add_parser("review", help="show one trace in the annotation layout")
    v.add_argument("case_id")
    v.add_argument("--traces")
    a = sub.add_parser("annotate", help="interactive open coding (resumable)")
    a.add_argument("--labels", required=True)
    a.add_argument("--traces")
    a.add_argument("--annotator", default="")
    a.add_argument("--redo", action="store_true", help="revisit already-labelled traces too")
    for name, helptext in (
        ("notes", "list failure notes grouped by first upstream step (input to axial coding)"),
        ("saturation", "distinct failure modes vs traces reviewed"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--labels")
    c = sub.add_parser("code", help="interactive axial coding of uncoded failure notes")
    c.add_argument("--labels", required=True)
    c.add_argument("--modes")
    k = sub.add_parser("rank", help="ranked failure list, Pareto chart, taxonomy sheet")
    k.add_argument("--labels")
    k.add_argument("--modes")
    k.add_argument("--taxonomy", help="write the taxonomy sheet CSV here")
    k.add_argument("--svg", help="write a Pareto chart SVG here")
    for name, helptext in (
        ("signals", "automatic flags per trace (where to look first)"),
        ("errors", "tool-call errors and what happened next"),
        ("retrieval", "retrieval hits and misses against expected documents"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--traces")
        sp.add_argument("--cases", help="cases JSONL (default: the module 3 cases)")
    m = sub.add_parser("compare", help="compare your labels with the reference labels")
    m.add_argument("--labels", required=True)
    m.add_argument("--reference", help="reference labels CSV (default: the module 3 reference)")
    args = p.parse_args(argv)

    if args.cmd == "run":
        spans = run_cases()
        traces = traces_by_case(spans)
        cost = sum(root_of(t)["attributes"].get("evalkit.cost.usd", 0) for t in traces.values())
        print(f"{len(traces)} traces, {len(spans)} spans, total cost ${cost:.4f} (replayed)")
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                for s in spans:
                    fh.write(json.dumps(s, sort_keys=True, ensure_ascii=False) + "\n")
            print(f"wrote {out}")
        return 0
    if args.cmd == "review":
        print(render_review(load_traces(args.traces)[args.case_id]))
        return 0
    if args.cmd == "annotate":
        n = annotate_session(load_traces(args.traces), args.labels, args.annotator, redo=args.redo)
        print(f"\nlabelled {n} traces this session -> {args.labels}")
        return 0
    if args.cmd == "notes":
        anns = [x for x in _labels(args) if x.failed]
        by: dict[str, list[Annotation]] = {}
        for x in anns:
            by.setdefault(x.first_upstream or "(not given)", []).append(x)
        for step, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
            print(f"\n## {step} ({len(items)})")
            for x in items:
                tag = f"  [{';'.join(x.modes)}]" if x.modes else ""
                print(f"- {x.case_id}: {x.note}{tag}")
        return 0
    if args.cmd == "code":
        known = list(load_modes(args.modes)) if args.modes else []
        n = code_session(args.labels, known)
        print(f"coded {n} traces")
        return 0
    if args.cmd == "saturation":
        print(render_saturation(saturation_curve(_labels(args))))
        return 0
    if args.cmd == "rank":
        anns = _labels(args)
        modes = load_modes(args.modes or reference_modes_path())
        rows = rank_modes(anns, modes)
        print(render_ranked(rows, anns))
        print("\nPareto (by number of traces):\n" + pareto_text(rows))
        print("\nFirst upstream failure:")
        for step, n in first_upstream_counts(anns).most_common():
            print(f"  {step:<26} {n}")
        if args.taxonomy:
            print(f"\nwrote {write_taxonomy_csv(rows, args.taxonomy)}")
        if args.svg:
            print(f"wrote {pareto_svg(rows, args.svg, 'MediaDoctor failure modes (module 3)')}")
        return 0
    if args.cmd in ("signals", "errors", "retrieval"):
        traces = load_traces(args.traces)
        cases = {c["id"]: c for c in load_cases(args.cases)}
        if args.cmd == "signals":
            table = signal_table(traces, cases)
            for cid, sig in table.items():
                print(f"{cid}  {', '.join(sig) or '-'}")
            counts = Counter(s for sig in table.values() for s in sig)
            print(f"\nflagged {sum(bool(s) for s in table.values())}/{len(table)} traces")
            for s, n in counts.most_common():
                print(f"  {s:<24} {n}")
        elif args.cmd == "errors":
            rows = tool_error_report(traces)
            for row in rows:
                print(f"{row['case_id']}  {row['tool']:<12} {row['outcome']:<13} {row['error']}")
            print(
                f"\n{len(rows)} failed tool calls: "
                + ", ".join(
                    f"{k} {v}" for k, v in Counter(r["outcome"] for r in rows).most_common()
                )
            )
        else:
            rows = retrieval_report(traces, cases)
            for row in rows:
                mark = "hit " if row["hit"] else "MISS"
                print(
                    f"{row['case_id']}  {mark} k={row['k']}  {row['query']!r} -> {row['returned']} (need {row['expected']})"
                )
            hits = sum(r["hit"] for r in rows)
            print(f"\n{hits}/{len(rows)} retrievals returned an expected document")
        return 0
    if args.cmd == "compare":
        mine = load_annotations(args.labels)
        ref = load_annotations(args.reference or reference_labels_path())
        ag = compare_verdicts(mine, ref)
        print(f"{ag.common} traces in common; pass/fail agreement {100 * ag.agreement:.0f}%")
        print(f"  you failed, reference passed: {', '.join(ag.only_mine_fail) or '-'}")
        print(f"  you passed, reference failed: {', '.join(ag.only_ref_fail) or '-'}")
        print("\nreference mode  ->  your modes on the same traces")
        for rm, cnt in mode_overlap(mine, ref).items():
            print(f"  {rm:<24} {dict(cnt)}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
