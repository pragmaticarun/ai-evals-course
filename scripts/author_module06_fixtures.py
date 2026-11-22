"""Write the module 6 fixtures: repeated runs of agent prompts v1 and v2, their reference labels,
reference answers, and a generic 1-10 helpfulness judge's scores.

No API key was used to write the course.

Runs. Run 1 of prompt v1 is module 5's run (fixtures/recorded/mediadoctor-m5.jsonl). This script
records run 1 of prompt v2 on the same 137 queries, and runs 2 to 5 of both prompts on the 37 dev
queries, through the real `run_agent` loop against a scripted client. Run n is stored as trial n-1
(see evalkit.fixtures), so each repeat replays its own answers.

How a run's behaviour is chosen (all randomness is a hash of prompt, run, and query):

- Each query has a tendency per prompt. Under v1 it is module 5's behaviour. Under v2 (which asks
  the agent to check the user's claims), an adopted false premise becomes a correction for 70% of
  queries and an ignored tool output becomes a correct answer for 35%. But v2 often writes its
  correction as a "Premise check:" line instead of "Likely cause:" (40% of corrected false-premise
  queries, and 20% of clear queries that v1 answered well), which breaks the answer format.
- In any run other than v1 run 1, a query follows its tendency with probability 0.7; otherwise its
  behaviour is drawn from the prompt's overall mix for that kind of query (MIX).

Labels follow from the behaviour, as in module 5 (data/labels/module06_runs.csv). The reference
answers are the scenario's correct cause and next step. The helpfulness scores are mostly 6 to 9,
loosely tied to length and confidence and barely to correctness (see `helpful`).
Every fixture record is tagged "source": "synthetic-authored".

Usage:  uv run python scripts/author_module06_fixtures.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from author_module03_fixtures import FakeClock, L, N, ScriptedClient, T  # noqa: E402
from author_module05_fixtures import DictClient, _line, behaviours, build  # noqa: E402
from module03_scenarios import S  # noqa: E402

from evalkit import LLM, Tracer  # noqa: E402
from mediadoctor import lab04, lab05, lab06  # noqa: E402
from mediadoctor.toolagent import run_agent  # noqa: E402

STAY = 0.7
MIX = {
    ("v1", "clear"): {"good": 0.45, "ignored": 0.15, "vague": 0.2, "cite_uncalled": 0.05,
                      "api": 0.07, "format": 0.08},
    ("v2", "clear"): {"good": 0.45, "ignored": 0.1, "vague": 0.2, "cite_uncalled": 0.05,
                      "api": 0.05, "premise_line": 0.15},
    ("v1", "missing-detail"): {"assume": 0.5, "ask": 0.5},
    ("v2", "missing-detail"): {"assume": 0.5, "ask": 0.5},
    ("v1", "false-premise"): {"adopt": 0.5, "correct": 0.5},
    ("v2", "false-premise"): {"adopt": 0.2, "correct": 0.5, "correct_premise_line": 0.3},
}  # fmt: skip


def _u(*parts: Any) -> float:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:12], 16) / 16**12


def _draw(mix: dict[str, float], u: float) -> str:
    acc = 0.0
    for name, w in mix.items():
        acc += w
        if u < acc:
            return name
    return name


def tendency(prompt: str, cid: str, base: str, row: dict[str, Any]) -> str:
    if prompt == "v1":
        return base
    u = _u("v2-tendency", cid)
    u2 = _u("v2-format", cid)
    if base == "adopt":
        if u >= 0.7:
            return "adopt"
        return "correct_premise_line" if u2 < 0.4 else "correct"
    if base == "correct":
        return "correct_premise_line" if u2 < 0.4 else "correct"
    if base == "ignored":
        return "good" if u < 0.35 else "ignored"
    if base == "good" and row["ambiguity"] == "clear":
        return "premise_line" if u < 0.2 else "good"
    return base


def usable(beh: str, row: dict[str, Any]) -> str:
    """Fall back where a scenario has no text for a pattern (as module 5 does)."""
    sc = S[lab04.scenario_for(row)]
    if beh in ("ignored", "api") and beh not in sc:
        return "vague"
    return beh


def behaviour(prompt: str, run: int, row: dict[str, Any], base: str) -> str:
    if (prompt, run) == ("v1", 1):
        return base
    if _u("stay", prompt, run, row["id"]) < STAY:
        return usable(tendency(prompt, row["id"], base, row), row)
    return usable(_draw(MIX[(prompt, row["ambiguity"])], _u("mix", prompt, run, row["id"])), row)


def build6(row: dict[str, Any], beh: str) -> tuple[list[list[dict]], dict[str, str]]:
    cid = row["id"]
    if beh not in ("premise_line", "correct_premise_line"):
        return build(row, beh, cid)
    script, ref = build(row, "good" if beh == "premise_line" else "correct", cid)
    text = script[-1][0]["text"]
    cause = _line(text, L)
    opener = "the question states no claim to correct. " if beh == "premise_line" else ""
    script[-1] = [T(text.replace(f"{L} {cause}", f"Premise check: {opener}{cause}"))]
    ref.update(
        verdict="fail",
        modes="format-violation",
        note="opened with 'Premise check:' instead of 'Likely cause:'",
        first_upstream="chat:answer",
    )
    return script, ref


def helpful(cid: str, prompt: str, modes: list[str], answer_text: str) -> tuple[int, str]:
    """A generic helpfulness judge: rewards confident, specific-sounding text, not correctness."""
    u = _u("helpful", prompt, cid)
    s = 7 + (u > 0.55) + (u > 0.9) - (u < 0.12)
    if "[tool:" in answer_text:
        s += 1
    if answer_text.startswith(f"{L} Not enough"):
        s -= 2
    if "vague-next-step" in modes and u < 0.5:
        s -= 1
    s = max(1, min(10, s))
    reason = {
        True: "Clear, specific diagnosis with a concrete next step and sources.",
        False: "Reasonable answer, though it could say more about the next step.",
    }[s >= 8]
    return s, reason


def write() -> None:
    rows = lab05.label_rows()
    base = dict(zip([r["id"] for r in rows], behaviours(rows), strict=True))
    m5 = lab05.annotations()
    clock = FakeClock()
    store_path = LLM(namespace=lab06.AGENT_NAMESPACE).store.path
    if store_path.exists():
        store_path.unlink()
    out_rows: list[dict[str, str]] = []
    counts: dict[tuple[str, int], int] = {}
    for prompt, run in lab06.run_keys():
        ids = lab06.ids_for(run)
        sel = [r for r in rows if r["id"] in set(ids)]
        if (prompt, run) == ("v1", 1):
            for r in sel:
                a = m5[r["id"]]
                out_rows.append(
                    {"prompt": prompt, "run": "1", "case_id": r["id"], "verdict": a.verdict,
                     "modes": ";".join(a.modes), "note": a.note}
                )  # fmt: skip
            continue
        scripts = {}
        for r in sel:
            beh = behaviour(prompt, run, r, base[r["id"]])
            scripts[r["id"]], ref = build6(r, beh)
            out_rows.append(
                {"prompt": prompt, "run": str(run), "case_id": r["id"], "verdict": ref["verdict"],
                 "modes": ref["modes"], "note": ref["note"]}
            )  # fmt: skip
        llm = LLM(
            namespace=lab06.AGENT_NAMESPACE,
            mode="record",
            client=ScriptedClient(scripts, {r["question"]: r["id"] for r in sel}, clock),
            source="synthetic-authored",
            clock=clock,
            trial=run - 1,
        )
        for r in sel:
            res = run_agent(
                r["question"], llm=llm, tracer=Tracer(), case_id=r["id"], prompt_version=prompt
            )
            assert res.stop_reason == "end_turn", (prompt, run, r["id"], res.stop_reason)
        counts[(prompt, run)] = len(sel)
    with lab06.labels_path().open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    with lab06.references_path().open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["case_id", "reference"])
        w.writeheader()
        for r in rows:
            sc = S[lab04.scenario_for(r)]
            w.writerow({"case_id": r["id"], "reference": f"{L} {sc['cause']}\n{N} {sc['next']}"})
    n_rec = len(LLM(namespace=lab06.AGENT_NAMESPACE).store.records())
    print(f"runs: {len(counts)} recorded, {sum(counts.values())} traces, {n_rec} records")
    print(f"labels: {len(out_rows)} rows")

    lab06.labels.cache_clear()
    lab06.items.cache_clear()
    lab06.reference_answers.cache_clear()
    table = {}
    for prompt in lab06.PROMPTS:
        modes = lab06.labels()[(prompt, 1)]
        for cid, item in lab06.items(prompt, 1).items():
            req = lab06.helpfulness_request(item)
            s, reason = helpful(cid, prompt, sorted(modes[cid]), item.answer)
            key = (req["system"], req["messages"][0]["content"])
            table.setdefault(key, json.dumps({"reason": reason, "score": s}))
    jl = LLM(
        namespace=lab06.JUDGE_NAMESPACE,
        mode="record",
        client=DictClient(table),
        source="synthetic-authored",
    )
    if jl.store.path.exists():
        jl.store.path.unlink()
    for prompt in lab06.PROMPTS:
        lab06.helpfulness(prompt, llm=jl)
    print(f"helpfulness fixtures: {len(jl.store.records())} records")


if __name__ == "__main__":
    write()
