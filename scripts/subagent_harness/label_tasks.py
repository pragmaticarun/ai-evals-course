"""Export the course's reference-labelling work as task files for annotator subagents, and build
the label CSVs from their answers.

    uv run python scripts/subagent_harness/label_tasks.py export <dir>
    uv run python scripts/subagent_harness/label_tasks.py build  <dir>

export writes <dir>/<set>/SPEC.md (what to label, the allowed values, the failure-mode taxonomy),
<dir>/<set>/items/<id>.md (one trace or run per file) and <dir>/<set>/batches/<n>.txt.
Annotators write <dir>/<set>/answers/<id>.json. build validates the answers and writes
data/labels/*.csv. Run it with the regenerated fixtures in place (plain replay mode).
"""

from __future__ import annotations

import csv
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from evalkit import repo_root
from mediadoctor import chat, lab03, lab04, lab05, lab06, lab07, lab09
from mediadoctor import experiments as X

ROOT = repo_root()
LABELS = ROOT / "data" / "labels"
ANN = "reference (subagent-authored, Claude Opus)"
BATCH = 25


def taxonomy(path: Path) -> str:
    modes = tomllib.loads(path.read_text())["mode"]
    return "\n".join(f"- `{m['id']}`: {m['name']}. {m['definition']}" for m in modes)


def mode_ids(path: Path) -> list[str]:
    return [m["id"] for m in tomllib.loads(path.read_text())["mode"]]


def _cut(s: str, n: int = 1800) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def render_trace(trace: Any, extra: str = "") -> str:
    """Question, every tool call with its result, the final answer, and the span order."""
    item = lab05.item_from_trace(trace)
    out = [f"# Item {item.case_id}", extra, "## User question", item.question, "", "## Tool calls"]
    if not item.tools:
        out.append("(none)")
    for i, (name, args, result, ok) in enumerate(item.tools, 1):
        out += [f"### {i}. {name} {args} -> {'ok' if ok else 'ERROR'}", "```", _cut(result), "```"]
    out += [
        "",
        "## Final answer",
        item.answer or "(empty)",
        "",
        "## Span order (for first_upstream)",
    ]
    out.append(_cut(lab03.render_review(trace), 4000))
    return "\n".join(x for x in out if x is not None)


def trace_specs() -> dict[str, dict[str, Any]]:
    tax3 = LABELS / "module03_modes.toml"
    taxp = LABELS / "production_modes_v2.toml"
    common = (
        "Label each item as a careful domain expert reviewing a MediaDoctor agent run. Decide "
        "whether the final answer is acceptable to send to the engineer who asked (verdict pass) "
        "or not (fail). For a fail, write a short open-coded note saying what went wrong, the "
        "failure modes that apply (ids from the taxonomy, ;-separated, most important first), and "
        "first_upstream: the first step where things went wrong, written as it appears in the span "
        "order (for example `execute_tool ffprobe`, `chat:plan` for the model's turn that chose the "
        "tools, `chat:answer` for the final answer turn, or `retrieval`). For a pass, leave modes "
        "and first_upstream empty and keep the note short (or empty).\n\nAnswer as JSON: "
        '{"verdict": "pass"|"fail", "note": "...", "first_upstream": "...", "modes": "a;b"}'
    )
    return {
        "m03": dict(tax=tax3, out="module03_reference.csv", text=common),
        "m04": dict(tax=taxp, out="module04_dev_reference.csv", text=common),
        "m05": dict(tax=taxp, out="module05_reference.csv", text=common),
        "m09ref": dict(tax=taxp, out="module09_reference.csv", text=common),
        "m09a": dict(tax=taxp, out="module09_annotator_a.csv", text=common, who="a"),
        "m09b": dict(tax=taxp, out="module09_annotator_b.csv", text=common, who="b"),
        "m06": dict(
            tax=taxp,
            out="module06_runs.csv",
            text=common.replace(', "first_upstream": "..."', "").replace(
                "and first_upstream: the first step", "(no first_upstream here; the first step"
            ),
        ),
    }


def items_for(name: str) -> dict[str, str]:
    if name == "m03":
        cases = {c["id"]: c for c in lab03.load_cases()}
        return {cid: render_trace(t) for cid, t in lab03.load_traces(None).items() if cid in cases}
    if name == "m04":
        rows = lab04.agent_slice(lab04.load_dataset())
        return {
            cid: render_trace(t) for cid, t in lab03.traces_by_case(lab04.run_slice(rows)).items()
        }
    if name == "m05":
        return {cid: render_trace(t) for cid, t in lab05.traces().items()}
    if name == "m06":
        out = {}
        for p, r in lab06.run_keys():
            if (p, r) == ("v1", 1):
                continue  # module 5's run: labelled in m05
            for cid, t in lab06.run_traces(p, r).items():
                out[f"{p}__{r}__{cid}"] = render_trace(t, f"(prompt {p}, run {r})")
        return out
    if name == "m09ref":
        return {cid: render_trace(t) for cid, t in lab03.traces_by_case(lab09.run_drift()).items()}
    if name in ("m09a", "m09b"):
        st = lab09.store()
        return {q.request_id: render_trace(st[q.request_id]) for q in lab09.queue()[:40]}
    if name == "m07agents":
        out = {}
        for cid, run in lab07.team_runs().items():
            ref = lab07.agent_refs()[cid]
            lines = [f"# Item {cid}", "## User question", run.question,
                     f"(reference route {';'.join(ref['expected_route'])}, tools {';'.join(ref['expected_tools'])})",
                     "## Steps"]  # fmt: skip
            for s in run.steps:
                args = json.dumps(s.args) if s.args else ""
                lines.append(
                    f"- [{s.kind}] {s.agent} {s.name} {args} {'' if s.ok else 'ERROR '}\n  {_cut(s.text, 1500)}"
                )
            lines += ["## Final answer", run.answer or "(empty)"]
            out[cid] = "\n".join(lines)
        return out
    if name == "m07rag":
        out = {}
        for rid, r in lab07.rag_runs().items():
            ctx = (
                "\n\n".join(f"[{c.id}] {_cut(c.text, 1200)}" for c in r.context) or "(no passages)"
            )
            out[rid] = (f"# Item {rid} (system {r.system}, query {r.query.id})\n## Question\n{r.query.text}\n"
                        f"## Retrieved passages\n{ctx}\n## Answer\n{r.answer}")  # fmt: skip
        return out
    if name == "m07sessions":
        out = {}
        for sid, s in lab07.sessions().items():
            sc = chat.scenarios()[s.scenario]
            out[sid] = (f"# Item {sid} (scenario {s.scenario}, prompt {s.prompt})\n## Scenario (what the "
                        f"simulated user knows)\n{json.dumps(sc.__dict__ if hasattr(sc, '__dict__') else str(sc), default=str)[:3000]}\n"
                        f"## Transcript\n{s.transcript()}")  # fmt: skip
        return out
    if name == "m11":
        out = {}
        for v in X.variants():
            for c in X.cases():
                t = X.run_task(c, v)
                a = t.attempts[-1]
                body = render_trace(
                    a.spans, f"(configuration {v}; attempts {len(t.attempts)}; final answer below)"
                )
                out[f"{v}__{c['id']}"] = (
                    body.replace(lab05.item_from_trace(a.spans).answer or "\0", t.answer)
                    if t.answer
                    else body
                )
        return out
    raise KeyError(name)


SPECS_EXTRA = {
    "m07agents": dict(
        out="module07_agents.csv",
        text=(
            "Each item is one run of MediaDoctor's planner + specialists + writer team. Judge the final "
            "answer the user gets: verdict pass (correct, grounded in what the specialists found, "
            "answers the question) or fail, with a short note naming the first thing that went wrong "
            "(wrong route, a brief that drops names the specialist needed, bad tool arguments, findings "
            "ignored by the writer, a generic answer...).\n\nAnswer as JSON: "
            '{"verdict": "pass"|"fail", "note": "..."}'
        ),
    ),
    "m07rag": dict(
        out="module07_rag.csv",
        text=(
            "Each item is a RAG answer: a question, the passages retrieved for it, and the answer. "
            "Label correct (yes: the answer is right and responsive for an Android media engineer), "
            "faithful (yes: every claim is supported by the retrieved passages; general knowledge or "
            "invented specifics make it no), relevant (yes: it addresses the question asked), and a "
            "short note.\n\nAnswer as JSON: "
            '{"correct": "yes"|"no", "faithful": "yes"|"no", "relevant": "yes"|"no", "note": "..."}'
        ),
    ),
    "m07sessions": dict(
        out="module07_sessions.csv",
        text=(
            "Each item is a multi-turn chat between MediaDoctor and a simulated user. Label: resolved "
            "(the user ends with a correct, usable diagnosis), gave_up_early (the agent stopped helping "
            "before it had to), re_ask (the agent asked for something the user already gave), "
            "needless_question (it asked a question it did not need), each yes/no; simulator_issue "
            "(empty, or a short note if the simulated user broke character, leaked the answer, or "
            "contradicted its scenario); and a short note.\n\nAnswer as JSON: "
            '{"resolved": "yes"|"no", "gave_up_early": "yes"|"no", "re_ask": "yes"|"no", '
            '"needless_question": "yes"|"no", "simulator_issue": "", "note": "..."}'
        ),
    ),
    "m11": dict(
        out="module11_reference.csv",
        text=(
            "Each item is one configuration's run on one query. Name the failure mode in the FINAL "
            "answer, or none:\n- `premise`: the answer adopts a false premise stated by the user\n"
            "- `ignored`: the answer contradicts a tool output\n- `skipped`: the answer relied on no "
            "tool output although the question named a file, device or log, or it cites tools that "
            "never ran\n- `format`: the answer lacks the Sources line (or the required format)\n"
            "- `none`: a correct, grounded answer\nIf several apply, pick the first in that order."
            '\n\nAnswer as JSON: {"mode": "premise"|"ignored"|"skipped"|"format"|"none"}'
        ),
    ),
}


def export(d: Path, only: list[str]) -> None:
    specs = {**trace_specs(), **SPECS_EXTRA}
    for name in only or list(specs):
        sp = specs[name]
        sd = d / name
        (sd / "items").mkdir(parents=True, exist_ok=True)
        (sd / "answers").mkdir(exist_ok=True)
        (sd / "batches").mkdir(exist_ok=True)
        text = sp["text"]
        if "tax" in sp:
            text += "\n\n## Failure-mode taxonomy (use these ids)\n" + taxonomy(sp["tax"])
        (sd / "SPEC.md").write_text(f"# Labelling task: {sp['out']}\n\n{text}\n", encoding="utf-8")
        items = items_for(name)
        for iid, body in items.items():
            (sd / "items" / f"{iid}.md").write_text(body, encoding="utf-8")
        ids = sorted(items)
        for i in range(0, len(ids), BATCH):
            (sd / "batches" / f"{i // BATCH:03d}.txt").write_text(
                "\n".join(ids[i : i + BATCH]) + "\n"
            )
        print(f"{name}: {len(ids)} items, {(len(ids) + BATCH - 1) // BATCH} batches")


def _answers(sd: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((sd / "answers").glob("*.json")):
        out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return out


def _yn(v: Any) -> str:
    return "yes" if str(v).strip().lower() in ("yes", "true", "y") else "no"


def build(d: Path, only: list[str]) -> None:
    specs = {**trace_specs(), **SPECS_EXTRA}
    for name in only or list(specs):
        sd = d / name
        if not (sd / "items").exists():
            continue
        ids = sorted(p.stem for p in (sd / "items").glob("*.md"))
        ans = _answers(sd)
        missing = [i for i in ids if i not in ans]
        if missing:
            print(f"{name}: {len(missing)} items unlabelled, e.g. {missing[:3]}; skipped")
            continue
        rows: list[dict[str, Any]] = []
        allowed = set(mode_ids(specs[name]["tax"])) if "tax" in specs[name] else set()
        if name in trace_specs() and name != "m06":
            who = specs[name].get("who")
            for i in ids:
                a = ans[i]
                modes = [m.strip() for m in str(a.get("modes", "")).split(";") if m.strip()]
                bad = [m for m in modes if m not in allowed]
                assert not bad, (name, i, bad)
                fail = a["verdict"] == "fail"
                rows.append({"case_id": i, "verdict": "fail" if fail else "pass",
                             "note": a.get("note", ""), "first_upstream": a.get("first_upstream", "") if fail else "",
                             "modes": ";".join(modes) if fail else "",
                             "annotator": who or ANN})  # fmt: skip
        elif name == "m06":
            m05 = {
                r["case_id"]: r for r in csv.DictReader((LABELS / "module05_reference.csv").open())
            }
            for p, r in lab06.run_keys():
                if (p, r) == ("v1", 1):
                    for cid in lab06.ids_for(1):
                        x = m05[cid]
                        rows.append({"prompt": p, "run": r, "case_id": cid, "verdict": x["verdict"],
                                     "modes": x["modes"], "note": x["note"]})  # fmt: skip
                    continue
                for cid in lab06.ids_for(r):
                    a = ans[f"{p}__{r}__{cid}"]
                    modes = [m.strip() for m in str(a.get("modes", "")).split(";") if m.strip()]
                    assert all(m in allowed for m in modes), (cid, modes)
                    fail = a["verdict"] == "fail"
                    rows.append({"prompt": p, "run": r, "case_id": cid, "verdict": a["verdict"],
                                 "modes": ";".join(modes) if fail else "", "note": a.get("note", "")})  # fmt: skip
        elif name == "m07agents":
            old = list(csv.DictReader((LABELS / "module07_agents.csv").open()))
            for r in old:
                a = ans[r["case_id"]]
                rows.append(
                    {**r, "verdict": a["verdict"], "note": a.get("note", ""), "annotator": ANN}
                )
        elif name == "m07rag":
            old = {
                (r["system"], r["query_id"]): r
                for r in csv.DictReader((LABELS / "module07_rag.csv").open())
            }
            runs = lab07.rag_runs()
            for i in ids:
                run, a = runs[i], ans[i]
                hit = old[(run.system, run.query.id)][
                    "retrieval_hit"
                ]  # retrieval is not a model output
                rows.append({"system": run.system, "query_id": run.query.id, "retrieval_hit": hit,
                             "correct": _yn(a["correct"]), "faithful": _yn(a["faithful"]),
                             "relevant": _yn(a["relevant"]), "note": a.get("note", ""), "annotator": ANN})  # fmt: skip
        elif name == "m07sessions":
            for i in ids:
                a = ans[i]
                rows.append({"session_id": i, **{k: _yn(a[k]) for k in ("resolved", "gave_up_early", "re_ask", "needless_question")},
                             "simulator_issue": a.get("simulator_issue", "") or "", "note": a.get("note", ""), "annotator": ANN})  # fmt: skip
        elif name == "m11":
            for i in ids:
                v, cid = i.split("__")
                mode = ans[i]["mode"]
                assert mode in ("premise", "ignored", "skipped", "format", "none"), (i, mode)
                rows.append({"variant": v, "case_id": cid, "mode": mode, "annotator": ANN})
        path = LABELS / specs[name]["out"]
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: wrote {len(rows)} rows to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    cmd, d, *only = sys.argv[1:]
    {"export": export, "build": build}[cmd](Path(d), only)
