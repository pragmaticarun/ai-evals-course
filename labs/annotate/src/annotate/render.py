"""Turn a trace into what a reviewer needs to see, not everything it contains.

Generic viewers show every attribute of every span. For these traces the useful view is: the
question, the answer with its citations checked, and each tool call with its output rendered the
way an engineer reads it (ffprobe fields as a table, codec_caps decoders as rows, logcat lines with
their level, retrieved documents by id). Attributes under `mediadoctor.sim.` are simulation
bookkeeping and are never shown, so review stays blind to where a trace came from.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from annotate.store import Trace, root_of

CITE_RE = re.compile(r"\[(tool|kb):([a-z0-9_-]+)\]")
LOG_LEVEL_RE = re.compile(r"\s([VDIWEF])\s")
HIDDEN_PREFIXES = ("mediadoctor.sim.",)


@dataclass
class View:
    """A tool result as the template should draw it."""

    kind: str  # "probe", "decoders", "log", "docs", "table", "error", "text"
    rows: list[Any] = field(default_factory=list)
    text: str = ""


@dataclass
class Node:
    span_id: str
    name: str
    op: str
    ms: float
    error: str
    summary: str
    view: View | None = None
    args: str = ""
    children: list[Node] = field(default_factory=list)
    depth: int = 0


def _parse(result: str) -> Any:
    try:
        return json.loads(result)
    except TypeError, ValueError:
        return None


def _flat(prefix: str, value: Any, out: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flat(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        for i, v in enumerate(value):
            _flat(f"{prefix}[{i}]", v, out)
    else:
        out.append((prefix, value if isinstance(value, str) else json.dumps(value)))


def tool_view(tool: str, result: str, error: str) -> View:
    if error:
        return View("error", text=error)
    data = _parse(result)
    if tool == "codec_caps" and isinstance(data, dict):
        rows = [
            (
                d.get("name", ""),
                "hardware" if d.get("hardware") else "software",
                ", ".join(d.get("profiles", [])),
                f"{d.get('max_width')}x{d.get('max_height')} @ {d.get('max_fps_at_max_size')} fps",
            )
            for d in data.get("decoders", [])
        ]
        facts = [
            (k, json.dumps(v) if not isinstance(v, str) else v)
            for k, v in data.items()
            if k != "decoders"
        ]
        return View("decoders", rows=[rows, facts])
    if tool == "ffprobe" and isinstance(data, dict):
        lines = []
        for st in data.get("streams", []):
            size = f"{st['width']}x{st['height']}" if "width" in st else ""
            keys = ("codec_name", "profile", "pix_fmt", "avg_frame_rate", "sample_rate", "channels")
            extra = {
                k: v
                for k, v in st.items()
                if k not in (*keys, "codec_type", "index", "width", "height")
            }
            main = " ".join(str(st[k]) for k in keys if k in st)
            more = " · ".join(f"{k} {v}" for k, v in extra.items())
            lines.append(
                (
                    f"#{st.get('index', '')} {st.get('codec_type', '')}",
                    " ".join(x for x in (main, size) if x),
                    more,
                )
            )
        facts = [
            (k, v if isinstance(v, str) else json.dumps(v))
            for k, v in data.items()
            if k != "streams"
        ]
        return View("probe", rows=[lines, facts])
    if tool == "logcat_grep" and isinstance(data, dict):
        lines = []
        for ln in data.get("lines", []):
            m = LOG_LEVEL_RE.search(ln)
            lines.append((m.group(1) if m else "", ln))
        return View("log", rows=lines, text=f"{data.get('matches', len(lines))} matching lines")
    if tool == "search_kb" and isinstance(data, (dict, list)):
        docs = data.get("results", []) if isinstance(data, dict) else data
        return View(
            "docs",
            rows=[(d.get("id", ""), d.get("title", "")) for d in docs if isinstance(d, dict)],
        )
    if isinstance(data, (dict, list)):
        rows: list[tuple[str, str]] = []
        _flat("", data, rows)
        return View("table", rows=rows[:60])
    return View("text", text=str(result))


def _summary(s: dict[str, Any]) -> str:
    a = s["attributes"]
    op = a.get("gen_ai.operation.name", "")
    if op == "chat":
        fin = ",".join(a.get("gen_ai.response.finish_reasons", []) or [])
        return (
            f"{a.get('gen_ai.response.model', a.get('gen_ai.request.model', ''))} · "
            f"{a.get('gen_ai.usage.input_tokens', 0)} in / {a.get('gen_ai.usage.output_tokens', 0)} out · {fin}"
        )
    if op == "retrieval":
        ids = a.get("mediadoctor.retrieval.doc_ids", []) or []
        return f"“{a.get('gen_ai.retrieval.query.text', '')}” → {', '.join(ids)}"
    if op == "invoke_agent":
        return f"{a.get('mediadoctor.steps', '?')} steps · ${a.get('evalkit.cost.usd', 0)}"
    return ""


def tree(trace: Trace) -> list[Node]:
    """Spans as a depth-first list (parents before children, siblings by start time)."""
    kids: dict[str | None, list[dict[str, Any]]] = {}
    for s in trace:
        kids.setdefault(s.get("parent_span_id"), []).append(s)
    for v in kids.values():
        v.sort(key=lambda s: s["start_time_unix_nano"])
    out: list[Node] = []

    def walk(s: dict[str, Any], depth: int) -> None:
        a = s["attributes"]
        op = a.get("gen_ai.operation.name", s["name"].split(" ")[0])
        err = s["status"]["message"] if s["status"]["code"] == "ERROR" else ""
        node = Node(
            s["span_id"], s["name"], op, s.get("duration_ms", 0.0), err, _summary(s), depth=depth
        )
        if op == "execute_tool":
            node.args = str(a.get("gen_ai.tool.call.arguments", ""))
            node.view = tool_view(
                str(a.get("gen_ai.tool.name")), str(a.get("gen_ai.tool.call.result", "")), err
            )
        out.append(node)
        for c in kids.get(s["span_id"], []):
            walk(c, depth + 1)

    for r in kids.get(None, []):
        walk(r, 0)
    return out


def evidence(trace: Trace) -> tuple[set[str], set[str], set[str]]:
    """(tools that succeeded, tools that failed, documents retrieved)."""
    ok, bad, docs = set(), set(), set()
    for s in trace:
        a = s["attributes"]
        if a.get("gen_ai.operation.name") == "execute_tool":
            (bad if s["status"]["code"] == "ERROR" else ok).add(str(a.get("gen_ai.tool.name")))
        docs.update(a.get("mediadoctor.retrieval.doc_ids", []) or [])
    return ok, bad - ok, docs


def answer_parts(trace: Trace) -> list[tuple[str, str]]:
    """The answer split into (css class, text) runs; citations are marked ok, failed, or unknown."""
    text = str(root_of(trace)["attributes"].get("mediadoctor.answer", ""))
    ok, bad, docs = evidence(trace)
    parts: list[tuple[str, str]] = []
    pos = 0
    for m in CITE_RE.finditer(text):
        parts.append(("", text[pos : m.start()]))
        kind, name = m.groups()
        if kind == "tool":
            cls = "cite-ok" if name in ok else "cite-bad" if name in bad else "cite-missing"
        else:
            cls = "cite-ok" if name in docs else "cite-missing"
        parts.append((cls, m.group(0)))
        pos = m.end()
    parts.append(("", text[pos:]))
    return parts


def header(trace: Trace) -> dict[str, Any]:
    r = root_of(trace)
    a = r["attributes"]
    return {
        "question": a.get("mediadoctor.question", ""),
        "ms": r.get("duration_ms", 0.0),
        "steps": a.get("mediadoctor.steps", ""),
        "app": a.get("mediadoctor.app.version", ""),
        "error": r["status"]["message"] if r["status"]["code"] == "ERROR" else "",
        "attrs": {k: v for k, v in a.items() if not k.startswith(HIDDEN_PREFIXES)},
    }
