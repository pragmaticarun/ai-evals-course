"""A tool-agnostic trace viewer for evalkit JSONL spans.

It only relies on the span fields (ids, parent ids, names, times, status, attributes), so it
works for any agent that writes this format, not just MediaDoctor.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

Span = dict[str, Any]


def fmt_ms(ms: float) -> str:
    return f"{ms / 1000:.2f}s" if ms >= 1000 else f"{ms:.0f}ms"


def group_traces(spans: list[Span]) -> dict[str, list[Span]]:
    traces: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        traces[s["trace_id"]].append(s)
    return dict(traces)


def root_of(spans: list[Span]) -> Span:
    roots = [s for s in spans if not s.get("parent_span_id")]
    return min(roots or spans, key=lambda s: s["start_time_unix_nano"])


@dataclass
class TraceSummary:
    trace_id: str
    name: str
    case_id: str
    duration_ms: float
    llm_calls: int
    tool_calls: int
    tool_errors: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: str


def summarize_trace(spans: list[Span]) -> TraceSummary:
    root = root_of(spans)
    op = lambda s: s["attributes"].get("gen_ai.operation.name")  # noqa: E731
    llm = [s for s in spans if op(s) == "chat"]
    tools = [s for s in spans if op(s) == "execute_tool"]
    errors = [s for s in spans if s["status"]["code"] == "ERROR"]
    return TraceSummary(
        trace_id=root["trace_id"],
        name=root["name"],
        case_id=str(root["attributes"].get("mediadoctor.case.id", "")),
        duration_ms=root["duration_ms"],
        llm_calls=len(llm),
        tool_calls=len(tools),
        tool_errors=sum(1 for s in tools if s["status"]["code"] == "ERROR"),
        input_tokens=sum(int(s["attributes"].get("gen_ai.usage.input_tokens", 0)) for s in llm),
        output_tokens=sum(int(s["attributes"].get("gen_ai.usage.output_tokens", 0)) for s in llm),
        cost_usd=sum(float(s["attributes"].get("evalkit.cost.usd", 0.0)) for s in llm),
        status="ERROR" if errors else root["status"]["code"],
    )


def render_table(spans: list[Span]) -> str:
    rows = [summarize_trace(t) for t in group_traces(spans).values()]
    rows.sort(key=lambda r: (r.case_id, r.trace_id))
    head = f"{'trace':<10} {'case':<7} {'time':>7} {'llm':>3} {'tools':>5} {'err':>3} {'in_tok':>7} {'out_tok':>7} {'cost $':>8}"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r.trace_id[:8]:<10} {r.case_id:<7} {fmt_ms(r.duration_ms):>7} {r.llm_calls:>3} "
            f"{r.tool_calls:>5} {r.tool_errors:>3} {r.input_tokens:>7} {r.output_tokens:>7} {r.cost_usd:>8.4f}"
        )
    tot_cost = sum(r.cost_usd for r in rows)
    tot_ms = sum(r.duration_ms for r in rows)
    lines.append("-" * len(head))
    lines.append(f"{len(rows)} traces, total time {fmt_ms(tot_ms)}, total cost ${tot_cost:.4f}")
    return "\n".join(lines)


# Attributes worth showing inline, per operation. Everything else appears with --all.
_KEY_ATTRS = {
    "chat": [
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.response.finish_reasons",
        "evalkit.cost.usd",
    ],
    "execute_tool": ["gen_ai.tool.call.arguments"],
    "retrieval": ["gen_ai.retrieval.query.text", "mediadoctor.retrieval.doc_ids"],
    "invoke_agent": ["mediadoctor.case.id", "mediadoctor.stop_reason", "evalkit.cost.usd"],
}


def _short(v: Any, width: int = 100) -> str:
    s = v if isinstance(v, str) else json.dumps(v)
    s = s.replace("\n", " ")
    return s if len(s) <= width else s[: width - 1] + "…"


def render_tree(spans: list[Span], show_all: bool = False, show_results: bool = False) -> str:
    children: dict[str | None, list[Span]] = defaultdict(list)
    for s in spans:
        children[s.get("parent_span_id")].append(s)
    for kids in children.values():
        kids.sort(key=lambda s: s["start_time_unix_nano"])
    root = root_of(spans)
    t0 = root["start_time_unix_nano"]
    lines: list[str] = [f"trace {root['trace_id']}"]

    def walk(s: Span, prefix: str, last: bool, is_root: bool) -> None:
        a = s["attributes"]
        op = a.get("gen_ai.operation.name", "")
        offset = (s["start_time_unix_nano"] - t0) / 1e6
        mark = "  !! ERROR: " + s["status"]["message"] if s["status"]["code"] == "ERROR" else ""
        branch = "" if is_root else ("└─ " if last else "├─ ")
        lines.append(
            f"{prefix}{branch}{s['name']}  [+{fmt_ms(offset)}, {fmt_ms(s['duration_ms'])}]{mark}"
        )
        child_prefix = prefix + ("" if is_root else ("   " if last else "│  "))
        keys = sorted(a) if show_all else [k for k in _KEY_ATTRS.get(str(op), []) if k in a]
        if (
            show_results
            and "gen_ai.tool.call.result" in a
            and "gen_ai.tool.call.result" not in keys
        ):
            keys.append("gen_ai.tool.call.result")
        for k in keys:
            lines.append(f"{child_prefix}    · {k} = {_short(a[k])}")
        kids = children.get(s["span_id"], [])
        for i, c in enumerate(kids):
            walk(c, child_prefix, i == len(kids) - 1, False)

    walk(root, "", True, True)
    return "\n".join(lines)


def find_trace(spans: list[Span], ref: str) -> list[Span]:
    """Find a trace by id prefix or by `mediadoctor.case.id`."""
    for tid, group in group_traces(spans).items():
        if tid.startswith(ref) or root_of(group)["attributes"].get("mediadoctor.case.id") == ref:
            return group
    raise KeyError(f"no trace matching {ref!r}")
