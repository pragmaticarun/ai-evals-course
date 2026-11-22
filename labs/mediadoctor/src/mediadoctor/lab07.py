"""Module 7 lab: evaluating architectures (RAG, multi-turn chat, multi-agent, multimodal).

    uv run mediadoctor-lab07 retrieval            # recall@k, precision@k, MRR, nDCG for 4 configs
    uv run mediadoctor-lab07 misses --topic codec # queries the improved retriever still misses
    uv run mediadoctor-lab07 rag                  # generation: judges, citations, attribution
    uv run mediadoctor-lab07 chat                 # simulated-user sessions: session and turn level
    uv run mediadoctor-lab07 session c05-v2       # one conversation, with its turn checks
    uv run mediadoctor-lab07 trajectories         # module 5's single-agent traces as trajectories
    uv run mediadoctor-lab07 agents               # planner + specialists: transition-failure matrix
    uv run mediadoctor-lab07 run m4q090           # one multi-agent trajectory, step by step
    uv run mediadoctor-lab07 vision               # frame judges and spectrogram answers
    uv run mediadoctor-lab07 report --out report.md

Replay mode (default) needs no API key. Every model output and every label in this lab is
synthetic-authored (see scripts/author_module07_fixtures.py).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import LLM, repo_root, text_of
from evalkit.judge import Confusion, Item, Verdict, confusion, load_judge, run_judge
from evalkit.retrieval import hit_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from evalkit.stats import bootstrap_ci, paired_bootstrap_diff, wilson_interval
from evalkit.trajectory import (
    first_failure,
    format_matrix,
    in_order,
    step_efficiency,
    tool_precision,
    tool_recall,
    transition_matrix,
)
from mediadoctor import chat, lab04, lab05, multiagent, rag, vision

JUDGE_NAMESPACE = "mediadoctor-m7-judges"
RAG_NAMESPACE = "mediadoctor-m7-rag"
K = 5
DRAWS = 2000
SEED = 7
CONFIGS = [(c, r) for c in rag.CHUNKERS for r in rag.RETRIEVERS]
TOPICS = ("codec", "streaming", "audio", "video")


def labels_dir() -> Path:
    return repo_root() / "data" / "labels"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (labels_dir() / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _ci(values: Sequence[float]) -> tuple[float, float, float]:
    return bootstrap_ci(list(values), lambda xs: sum(xs) / len(xs), draws=DRAWS, seed=SEED)


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson_interval(k, n)
    return f"{k}/{n} = {k / n:.2f} [{lo:.2f}, {hi:.2f}]" if n else "n/a"


def judge_llm() -> LLM:
    return LLM(namespace=JUDGE_NAMESPACE)


def spec(name: str):
    return load_judge(repo_root() / "config" / "judges" / f"{name}.v1.toml")


# --- Part A1: retrieval -------------------------------------------------------------------------------


def ranked_sections(q: rag.Query, chunker: str, retriever: str, k: int = K) -> list[str]:
    """The top-k chunks, each credited to its section (so both chunkers use the same labels)."""
    return [c.section for c in rag.search(q.text, chunker, retriever, k)]


@dataclass(frozen=True)
class QueryScores:
    query: rag.Query
    ranked: tuple[str, ...]
    recall: float
    precision: float
    hit: float
    rr: float
    ndcg: float


def score_queries(chunker: str, retriever: str, k: int = K) -> list[QueryScores]:
    out = []
    for q in rag.queries():
        r = ranked_sections(q, chunker, retriever, k)
        out.append(
            QueryScores(q, tuple(r), recall_at_k(r, q.relevant, k), precision_at_k(r, q.relevant, k),
                        hit_at_k(r, q.answering, k), reciprocal_rank(r, q.relevant),
                        ndcg_at_k(r, q.grades, k))
        )  # fmt: skip
    return out


def retrieval_rows(k: int = K) -> list[dict[str, Any]]:
    rows = []
    for c, r in CONFIGS:
        s = score_queries(c, r, k)
        rec = _ci([x.recall for x in s])
        row = {
            "config": f"{c}+{r}",
            "recall": rec,
            "precision": sum(x.precision for x in s) / len(s),
            "mrr": sum(x.rr for x in s) / len(s),
            "ndcg": sum(x.ndcg for x in s) / len(s),
            "hit": sum(x.hit for x in s) / len(s),
        }
        for t in TOPICS:
            ts = [x.recall for x in s if x.query.topic == t]
            row[t] = sum(ts) / len(ts)
        rows.append(row)
    return rows


def recall_diff(a: tuple[str, str], b: tuple[str, str], k: int = K, topic: str | None = None):
    """Paired bootstrap on per-query recall@k: same queries, two retrieval configs."""
    sa = [x for x in score_queries(*a, k) if topic in (None, x.query.topic)]
    sb = [x for x in score_queries(*b, k) if topic in (None, x.query.topic)]
    diffs = [y.recall - x.recall for x, y in zip(sa, sb, strict=True)]
    return _ci(diffs), len(diffs)


def print_retrieval(k: int = K) -> None:
    print(
        f"Retrieval over data/kb_v2 ({len(rag.sections())} sections), {len(rag.queries())} labelled queries, k={k}\n"
    )
    print(f"{'config':<16}{'recall@k [95% CI]':>24}{'P@k':>6}{'MRR':>6}{'nDCG':>6}{'hit':>6}  "
          + "".join(f"{t:>10}" for t in TOPICS))  # fmt: skip
    for row in retrieval_rows(k):
        m, lo, hi = row["recall"]
        print(f"{row['config']:<16}{m:>8.2f} [{lo:.2f}, {hi:.2f}]{row['precision']:>8.2f}{row['mrr']:>6.2f}"
              f"{row['ndcg']:>6.2f}{row['hit']:>6.2f}  " + "".join(f"{row[t]:>10.2f}" for t in TOPICS))  # fmt: skip
    base, best = ("fixed", "keyword"), ("section", "bm25")
    for topic in (None, "codec"):
        (d, lo, hi), n = recall_diff(base, best, k, topic)
        print(f"\nfixed+keyword -> section+bm25, recall@{k} ({topic or 'all'} queries, n={n}): "
              f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]")  # fmt: skip
    print(
        "\nTopic columns are recall@k per topic. Precision@k is low by construction: most queries"
    )
    print("have one or two relevant sections, so even a perfect top 5 has precision 0.2 to 0.4.")


def misses(chunker: str = "section", retriever: str = "bm25", topic: str | None = None, k: int = K):
    return [x for x in score_queries(chunker, retriever, k)
            if x.recall < 1 and topic in (None, x.query.topic)]  # fmt: skip


# --- Part A2: generation, judged and attributed -----------------------------------------------------


@dataclass(frozen=True)
class RagRun:
    system: str
    query: rag.Query
    context: tuple[rag.Chunk, ...]
    answer: str

    @property
    def id(self) -> str:
        return f"{self.system}:{self.query.id}"

    @property
    def hit(self) -> bool:
        """Retrieval succeeded: a passage that answers the query is in the context."""
        return any(c.section in self.query.answering for c in self.context)

    def item(self) -> Item:
        args = json.dumps({"query": self.query.text})
        return Item(self.id, self.query.text, self.answer,
                    (("search_kb", args, rag.format_context(list(self.context)), True),))  # fmt: skip


@cache
def rag_runs() -> dict[str, RagRun]:
    llm = LLM(namespace=RAG_NAMESPACE)
    out = {}
    for system in rag.SYSTEMS:
        for q in rag.queries():
            ctx = rag.context_for(q.text, system)
            ans = text_of(llm.create(**rag.rag_request(q.text, ctx))).strip()
            r = RagRun(system, q, tuple(ctx), ans)
            out[r.id] = r
    return out


@cache
def rag_labels() -> dict[str, dict[str, Any]]:
    return {f"{r['system']}:{r['query_id']}": {"correct": r["correct"] == "yes",
            "faithful": r["faithful"] == "yes", "relevant": r["relevant"] == "yes", "note": r["note"]}
            for r in _read_csv("module07_rag.csv")}  # fmt: skip


def rag_pass(run_id: str) -> bool:
    lab = rag_labels()[run_id]
    return lab["correct"] and lab["faithful"]


def cited(answer: str) -> list[str]:
    return rag.CITE.findall(answer)


def citation_checks(r: RagRun) -> dict[str, bool]:
    """valid: every cited id is a passage in the context. supports: some cited passage is relevant."""
    ids = cited(r.answer)
    in_ctx = {c.id: c for c in r.context}
    return {
        "valid": all(i in in_ctx for i in ids),
        "supports": any(i in in_ctx and in_ctx[i].section in r.query.relevant for i in ids),
        "cites": bool(ids),
    }


@cache
def rag_verdicts(name: str) -> dict[str, Verdict]:
    return run_judge(
        judge_llm().create, spec(name), [r.item() for r in rag_runs().values()], {}, text_of
    )


def rag_judge_confusion(name: str) -> Confusion:
    key = {"faithfulness": "faithful", "answer-relevance": "relevant"}[name]
    human = {i: lab[key] for i, lab in rag_labels().items()}
    return confusion(human, {i: v.passed for i, v in rag_verdicts(name).items()})


def attribution(system: str) -> Counter[str]:
    """Separate retrieval failures from generation failures, run by run."""
    c: Counter[str] = Counter()
    for r in rag_runs().values():
        if r.system != system:
            continue
        ok = rag_pass(r.id)
        c[
            ("pass" if ok else "generation failure")
            if r.hit
            else ("pass despite miss" if ok else "retrieval failure")
        ] += 1
    return c


def print_rag() -> None:
    runs = rag_runs()
    print(f"RAG answers: {len(runs)} runs ({len(rag.queries())} queries x {len(rag.SYSTEMS)} systems, "
          f"top {rag.CONTEXT_K} passages)\n")  # fmt: skip
    for system, (c, r) in rag.SYSTEMS.items():
        ids = [i for i, x in runs.items() if x.system == system]
        k = sum(rag_pass(i) for i in ids)
        hits = sum(runs[i].hit for i in ids)
        cc = [citation_checks(runs[i]) for i in ids]
        print(f"{system} ({c}+{r}): pass (correct and faithful) {fmt_rate(k, len(ids))}")
        print(
            f"    retrieval hit@{rag.CONTEXT_K} (an answering passage in context): {fmt_rate(hits, len(ids))}"
        )
        print(f"    citations valid {sum(x['valid'] for x in cc)}/{len(ids)}, "
              f"cite a relevant passage {sum(x['supports'] for x in cc)}/{len(ids)}")  # fmt: skip
        a = attribution(system)
        print("    attribution: " + ", ".join(f"{n} {a[n]}" for n in
              ("pass", "generation failure", "retrieval failure", "pass despite miss")))  # fmt: skip
        gen = a["pass"] / (a["pass"] + a["generation failure"])
        print(
            f"    pass rate when retrieval hit: {gen:.2f} (the ceiling if retrieval were perfect)"
        )
    print()
    for name in ("faithfulness", "answer-relevance"):
        print(f"{name} judge vs labels (PASS = positive): {rag_judge_confusion(name)}")
    base = [rag_pass(f"baseline:{q.id}") for q in rag.queries()]
    imp = [rag_pass(f"improved:{q.id}") for q in rag.queries()]
    print(
        f"\nbaseline -> improved, paired: {paired_bootstrap_diff(base, imp, draws=DRAWS, seed=SEED)}"
    )


# --- Part B: multi-turn chat with a simulated user -------------------------------------------------


@cache
def sessions() -> dict[str, chat.Session]:
    return chat.run_sessions()


@cache
def session_labels() -> dict[str, dict[str, str]]:
    return {r["session_id"]: r for r in _read_csv("module07_sessions.csv")}


def _yes(v: str) -> bool:
    return v == "yes"


def gave_up_items() -> list[Item]:
    return [
        Item(s.id, chat.scenarios()[s.scenario].opening, s.transcript())
        for s in sessions().values()
    ]


@cache
def gave_up_verdicts() -> dict[str, Verdict]:
    return run_judge(judge_llm().create, spec("gave-up-early"), gave_up_items(), {}, text_of)


def gave_up_confusion(judged: dict[str, bool | None] | None = None) -> Confusion:
    """PASS = did not give up early. Labels: gave_up_early yes = FAIL."""
    human = {i: not _yes(r["gave_up_early"]) for i, r in session_labels().items()}
    judged = judged if judged is not None else {i: v.passed for i, v in gave_up_verdicts().items()}
    return confusion(human, judged)


def chat_rows() -> list[dict[str, Any]]:
    rows = []
    for s in sessions().values():
        sc = chat.scenarios()[s.scenario]
        turns = chat.turn_checks(sc, s)
        lab = session_labels()[s.id]
        rows.append({
            "id": s.id, "prompt": s.prompt, "scenario": sc.id, "missing": bool(sc.missing),
            "resolved": chat.resolved(sc, s), "resolved_label": _yes(lab["resolved"]),
            "gave_up": _yes(lab["gave_up_early"]),
            "asked_when_needed": chat.asked_when_needed(sc, s),
            "re_ask": any(t["re_ask"] for t in turns), "needless": any(t["needless"] for t in turns),
            "one_question": all(t["one_question"] for t in turns),
            "user_turns": len(s.user_turns), "agent_turns": len(s.agent_turns),
            "sim_problems": chat.simulator_problems(sc, s),
            "sim_label": lab["simulator_issue"],
        })  # fmt: skip
    return rows


def print_chat() -> None:
    rows = chat_rows()
    print(f"{len(rows)} sessions: {len(chat.scenarios())} scenarios x prompts {', '.join(chat.CHAT_PROMPTS)}; "
          f"at most {chat.MAX_USER_TURNS} user turns\n")  # fmt: skip
    print("Session level")
    for p in chat.CHAT_PROMPTS:
        rs = [r for r in rows if r["prompt"] == p]
        res = [r for r in rs if r["resolved"]]
        miss = [r for r in rs if r["missing"]]
        print(f"  {p}: resolved {fmt_rate(len(res), len(rs))}; gave up early {sum(r['gave_up'] for r in rs)}; "
              f"mean user turns {sum(r['user_turns'] for r in rs) / len(rs):.2f}")  # fmt: skip
        print(f"      opening lacked a needed fact ({len(miss)}): asked first {sum(bool(r['asked_when_needed']) for r in miss)}, "
              f"resolved {sum(r['resolved'] for r in miss)}; had everything ({len(rs) - len(miss)}): "
              f"resolved {sum(r['resolved'] for r in rs if not r['missing'])}")  # fmt: skip
    agree = sum(r["resolved"] == r["resolved_label"] for r in rows)
    print(f"  resolved (code check) agrees with the labels on {agree}/{len(rows)} sessions")
    print("\nTurn level (any turn in the session)")
    for p in chat.CHAT_PROMPTS:
        rs = [r for r in rows if r["prompt"] == p]
        print(f"  {p}: re-asked a known fact {sum(r['re_ask'] for r in rs)}, needless question "
              f"{sum(r['needless'] for r in rs)}, more than one question in a turn "
              f"{sum(not r['one_question'] for r in rs)}")  # fmt: skip
    pa = [r["resolved"] for r in rows if r["prompt"] == "v1"]
    pb = [r["resolved"] for r in rows if r["prompt"] == "v2"]
    print(
        f"\nv1 -> v2 resolved, paired by scenario: {paired_bootstrap_diff(pa, pb, draws=DRAWS, seed=SEED)}"
    )
    print(f"\ngave-up-early judge vs labels (PASS = kept going): {gave_up_confusion()}")
    print("\nSimulated user checks (validate the simulator before trusting the sessions)")
    for r in rows:
        if r["sim_problems"] or r["sim_label"]:
            print(
                f"  {r['id']}: code: {'; '.join(r['sim_problems']) or '-'} | label: {r['sim_label'] or '-'}"
            )


# --- Part C1: module 5's single-agent traces as trajectories ---------------------------------------


def trajectory_rows() -> list[dict[str, Any]]:
    rows = []
    labels = lab05.annotations()
    for r in lab05.label_rows():
        if r["ambiguity"] == "missing-detail":
            continue  # the right trajectory there is to ask, not to call tools (module 4)
        it = lab05.items()[r["id"]]
        called = [name for name, _, _, _ in it.tools]
        expected = list(r["expected_tools"])
        chats = sum(1 for s in lab05.traces()[r["id"]]
                    if s["attributes"].get("gen_ai.operation.name") == "chat")  # fmt: skip
        minimal = 1 + (1 if expected else 0)
        rows.append({
            "id": r["id"], "split": r["split"], "expected": expected, "called": called,
            "recall": tool_recall(expected, called),
            "precision": tool_precision([*expected, "search_kb"], called),
            "in_order": in_order([t for t in expected if t != "search_kb"], called),
            "arg_errors": sum(1 for *_, ok in it.tools if not ok),
            "efficiency": step_efficiency(minimal, chats),
            "passed": labels[r["id"]].verdict == "pass",
        })  # fmt: skip
    return rows


def print_trajectories() -> None:
    rows = trajectory_rows()
    n = len(rows)
    print(
        f"Module 5's traces, scored as trajectories against dataset v1's expected_tools: {n} runs"
    )
    print(
        "(missing-detail queries are left out: their right trajectory is a question, not a tool)\n"
    )
    for name, test in (("all expected tools called", lambda r: r["recall"] == 1),
                       ("no unexpected tools", lambda r: r["precision"] == 1),
                       ("no tool errors", lambda r: r["arg_errors"] == 0)):  # fmt: skip
        good = [r for r in rows if test(r)]
        bad = [r for r in rows if not test(r)]
        pg = sum(r["passed"] for r in good) / len(good) if good else float("nan")
        pb = sum(r["passed"] for r in bad) / len(bad) if bad else float("nan")
        print(
            f"{name:<28} {len(good):>3}/{n}   outcome pass rate: when true {pg:.2f}, when false {pb:.2f}"
        )
    eff = [r["efficiency"] for r in rows]
    print(f"\nmean step efficiency (minimal model calls / actual): {sum(eff) / n:.2f}")
    print(
        "\nThe right tools are necessary, not sufficient: most runs that called them still failed"
    )
    print(
        "on the answer (ignored output, vague next step, accepted premise). The outcome stays the"
    )
    print("headline; trajectory checks say where to look.")


# --- Part C2: planner + specialists ----------------------------------------------------------------


@cache
def agent_refs() -> dict[str, dict[str, Any]]:
    out = {}
    for r in _read_csv("module07_agents.csv"):
        out[r["case_id"]] = {**r, "expected_route": r["expected_route"].split(";"),
                             "expected_tools": r["expected_tools"].split(";")}  # fmt: skip
    return out


@cache
def team_runs() -> dict[str, multiagent.Run]:
    llm = LLM(namespace=multiagent.NAMESPACE)
    rows = {r["id"]: r for r in lab04.load_dataset()}
    return {cid: multiagent.run_team(rows[cid]["question"], cid, llm) for cid in agent_refs()}


def entities(question: str) -> set[str]:
    return {m.group(0).lower() for m in lab04.NAMES.finditer(question)}


def states(run: multiagent.Run) -> list[tuple[str, bool]]:
    """The run as a sequence of (state, succeeded), judged against the reference trajectory."""
    ref = agent_refs()[run.case_id]
    out: list[tuple[str, bool]] = []
    need = entities(run.question)
    for s in run.steps:
        if s.kind == "plan":
            out.append(("plan", run.route == ref["expected_route"]))
        elif s.kind == "handoff":
            out.append(("handoff", all(e in s.text.lower() for e in need)))
        elif s.kind == "tool":
            out.append((s.name, s.ok))
    ok_tools = {s.name for s in run.tool_steps if s.ok}
    out.append(("evidence", {t for t in ref["expected_tools"] if t != "search_kb"} <= ok_tools))
    out.append(("answer", ref["verdict"] == "pass"))
    return out


def failure_of(run: multiagent.Run) -> tuple[str, str] | None:
    if agent_refs()[run.case_id]["verdict"] == "pass":
        return None
    st = states(run)
    return first_failure([s for s, _ in st], lambda i, _: st[i][1])


def minimal_calls(case_id: str) -> int:
    return 2 + 2 * len(agent_refs()[case_id]["expected_route"])


def print_agents() -> None:
    runs = team_runs()
    refs = agent_refs()
    n = len(runs)
    k = sum(refs[c]["verdict"] == "pass" for c in runs)
    print(f"Planner + specialists on {n} dev and test queries: pass {fmt_rate(k, n)}\n")
    rows, cols, counts = transition_matrix(failure_of(r) for r in runs.values())
    print(
        "Transition-failure matrix (failed runs only): row = last state that succeeded, "
        "column = first state that failed\n"
    )
    print(format_matrix(rows, cols, counts))
    errs = Counter()
    for r in runs.values():
        st = states(r)
        errs["wrong route"] += not st[0][1]
        errs["brief lost a name"] += any(s == "handoff" and not ok for s, ok in st)
        errs["tool call errors"] += sum(1 for s in r.tool_steps if not s.ok)
    print("\nHandoff and tool errors (all runs): " + ", ".join(f"{k} {v}" for k, v in errs.items()))
    eff = defaultdict(list)
    for c, r in runs.items():
        eff[refs[c]["verdict"]].append(step_efficiency(minimal_calls(c), r.model_calls))
    for v, xs in sorted(eff.items(), reverse=True):
        print(
            f"step efficiency, {v}ed runs: mean {sum(xs) / len(xs):.2f} (n={len(xs)}, below 1.0: {sum(x < 1 for x in xs)})"
        )


def show_run(case_id: str) -> None:
    run = team_runs()[case_id]
    ref = agent_refs()[case_id]
    print(f"{case_id}: {run.question}\nreference route {ref['expected_route']}, tools {ref['expected_tools']}, "
          f"verdict {ref['verdict']} ({ref['note']})\n")  # fmt: skip
    for s in run.steps:
        txt = s.text.replace("\n", " ")
        print(f"[{s.kind:<8}] {s.agent:<9} {s.name} {json.dumps(s.args) if s.args else ''} "
              f"{'' if s.ok else 'ERROR '}{txt[:150]}")  # fmt: skip
    print(f"\nstates: {states(run)}\nfirst failure: {failure_of(run)}; model calls {run.model_calls}, "
          f"minimal {minimal_calls(case_id)}")  # fmt: skip


# --- Part D: images ----------------------------------------------------------------------------------


@cache
def frame_verdicts(name: str) -> dict[str, Verdict]:
    llm = LLM(namespace=vision.NAMESPACE)
    sp = spec(name)
    out = {}
    for img in vision.images().values():
        if img.kind == "frame":
            from evalkit.judge import parse_verdict

            out[img.name] = parse_verdict(
                img.name, text_of(llm.create(**vision.judge_request(sp, img.name)))
            )
    return out


def frame_rows() -> list[dict[str, Any]]:
    rows = []
    for name, artifact in (("frame-blocking", "blocking"), ("frame-banding", "banding")):
        v = frame_verdicts(name)
        for img in vision.images().values():
            if img.kind == "frame":
                rows.append({"judge": name, "image": img.name, "artifact": img.artifact,
                             "severity": img.severity, "present": img.artifact == artifact,
                             "flagged": v[img.name].passed is False})  # fmt: skip
    return rows


@cache
def spectrogram_answers() -> dict[str, str]:
    llm = LLM(namespace=vision.NAMESPACE)
    return {img.name: text_of(llm.create(**vision.spectrogram_request(img.name))).strip()
            for img in vision.images().values() if img.kind == "spectrogram"}  # fmt: skip


def print_vision() -> None:
    rows = frame_rows()
    print("Vision judges on decoded frames (labels from how each frame was made)\n")
    for name in ("frame-blocking", "frame-banding"):
        rs = [r for r in rows if r["judge"] == name]
        pos = [r for r in rs if r["present"]]
        neg = [r for r in rs if not r["present"]]
        print(f"{name}: detects the artifact {fmt_rate(sum(r['flagged'] for r in pos), len(pos))}; "
              f"leaves other frames alone {fmt_rate(sum(not r['flagged'] for r in neg), len(neg))}")  # fmt: skip
        for sev in ("severe", "mild"):
            s = [r for r in pos if r["severity"] == sev]
            print(f"    {sev:<7} detected {sum(r['flagged'] for r in s)}/{len(s)}")
        fa = [r["image"] for r in neg if r["flagged"]]
        print(f"    false alarms: {', '.join(fa) or 'none'}")
    print("\nSpectrogram answers (code check: the Defect line matches the label)")
    ok = 0
    for name, ans in spectrogram_answers().items():
        img = vision.images()[name]
        got = vision.defect_of(ans)
        ok += got == img.artifact
        print(
            f"  {name:<22} label {img.artifact:<9} answer {got or '?':<9} {'ok' if got == img.artifact else 'WRONG'}"
        )
    print(f"  correct {fmt_rate(ok, len(spectrogram_answers()))}")


# --- Report ----------------------------------------------------------------------------------------


def report() -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for title, fn in (("Retrieval", print_retrieval), ("RAG generation", print_rag),
                          ("Multi-turn chat", print_chat), ("Single-agent trajectories", print_trajectories),
                          ("Planner and specialists", print_agents), ("Images", print_vision)):  # fmt: skip
            print(f"## {title}\n\n```text")
            fn()
            print("```\n")
    return "# MediaDoctor module 7 report: evaluating each architecture\n\n" + buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mediadoctor-lab07", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "retrieval", help="retrieval metrics for every chunker and retriever"
    ).add_argument("--k", type=int, default=K)
    m = sub.add_parser("misses", help="queries a retrieval config does not fully recall")
    m.add_argument("--config", default="section+bm25", choices=[f"{c}+{r}" for c, r in CONFIGS])
    m.add_argument("--topic", choices=TOPICS)
    sub.add_parser("rag", help="RAG answers: judges, citations, retrieval vs generation failures")
    sub.add_parser("chat", help="simulated-user sessions, session and turn level")
    sub.add_parser("session", help="one conversation with its turn checks").add_argument(
        "session_id"
    )
    sub.add_parser("trajectories", help="module 5 traces scored as trajectories")
    sub.add_parser("agents", help="planner + specialists: transition-failure matrix")
    sub.add_parser("run", help="one multi-agent run, step by step").add_argument("case_id")
    sub.add_parser("vision", help="frame judges and spectrogram answers")
    sub.add_parser("report", help="everything, as Markdown").add_argument("--out")
    args = p.parse_args(argv)

    if args.cmd == "retrieval":
        print_retrieval(args.k)
    elif args.cmd == "misses":
        c, r = args.config.split("+")
        for x in misses(c, r, args.topic):
            print(f"{x.query.id} [{x.query.topic}] recall@{K} {x.recall:.2f}  {x.query.text}")
            print(f"    relevant: {', '.join(sorted(x.query.relevant))}")
            print(f"    top {K}:   {', '.join(x.ranked)}")
    elif args.cmd == "rag":
        print_rag()
    elif args.cmd == "chat":
        print_chat()
    elif args.cmd == "session":
        s = sessions()[args.session_id]
        sc = chat.scenarios()[s.scenario]
        print(s.transcript())
        print("\nturn checks:")
        for t in chat.turn_checks(sc, s):
            print(f"  {t}")
        print(f"resolved: {chat.resolved(sc, s)}; label: {session_labels()[s.id]}")
        print(f"simulator problems: {chat.simulator_problems(sc, s) or 'none'}")
    elif args.cmd == "trajectories":
        print_trajectories()
    elif args.cmd == "agents":
        print_agents()
    elif args.cmd == "run":
        show_run(args.case_id)
    elif args.cmd == "vision":
        print_vision()
    elif args.cmd == "report":
        text = report()
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
