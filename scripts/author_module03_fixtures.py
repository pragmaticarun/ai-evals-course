"""Write the module 3 trace set: 100 synthetic-authored MediaDoctor runs plus reference labels.

As in module 2, no API key was used to write the course. Each run combines a scenario from
scripts/module03_scenarios.py with a behaviour pattern (a correct run, or one planted failure),
and the real `run_agent` loop records it against a scripted fake client. So the requests hold the
real tool schemas and real tool results; only the model's turns are hand-written. Every fixture
record is tagged "source": "synthetic-authored".

Outputs:
  data/datasets/module03_cases.jsonl        100 cases (question, scenario, expected tools and docs)
  fixtures/recorded/mediadoctor-m3.jsonl    recorded model responses (replayed by the lab)
  data/labels/module03_reference.csv        the course's reference annotations (answer key)

The reference annotations are what a careful domain expert would write for these traces; they are
synthetic too, written from templates with some variation in wording, and are labelled as such.

Usage:  uv run python scripts/author_module03_fixtures.py
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from module03_scenarios import PLAN, S  # noqa: E402

from evalkit import LLM, Tracer, repo_root  # noqa: E402
from evalkit.fixtures import canonical_json  # noqa: E402
from mediadoctor.kb import load_kb  # noqa: E402
from mediadoctor.toolagent import run_agent  # noqa: E402

NAMESPACE = "mediadoctor-m3"
SEED = 82  # chosen so the review order shows saturation clearly (see check_order below)
L, N, SRC = "Likely cause:", "Next step:", "Sources:"

MODES = {
    "ignored": ["ignored-tool-output"],
    "api": ["wrong-api-detail"],
    "miss": ["retrieval-miss"],
    "fabricated": ["wrong-tool-args", "fabricated-evidence"],
    "giveup": ["wrong-tool-args"],
    "cite_uncalled": ["skipped-investigation", "fabricated-evidence"],
    "skipped": ["skipped-investigation"],
    "redundant": ["redundant-steps"],
    "vague": ["vague-next-step"],
    "format": ["format-violation"],
    "good": [],
    "recovered": [],
}

WHAT = {"ffprobe": "file", "codec_caps": "device", "logcat_grep": "log file"}


def T(text: str) -> dict:
    return {"type": "text", "text": text}


def answer(cause: str, nxt: str, src: str, sources_line: bool = True) -> list[dict]:
    text = f"{L} {cause}\n{N} {nxt}"
    if sources_line:
        text += f"\n{SRC} {src}"
    return [T(text)]


def pick(options: Any, i: int) -> Any:
    return options[i % len(options)] if isinstance(options, list) else options


def is_search(turn: list) -> bool:
    return all(name == "search_kb" for name, _ in turn)


def build(sid: str, pattern: str, i: int, cid: str) -> tuple[list[list[dict]], dict[str, Any]]:
    """Return (scripted assistant turns, reference annotation) for one run."""
    sc = S[sid]
    turns: list[list[tuple[str, dict]]] = [list(t) for t in sc["turns"]]
    final = answer(sc["cause"], sc["next"], sc["src"])
    note, upstream = "", ""
    n = 0

    def U(name: str, args: dict) -> dict:
        nonlocal n
        n += 1
        return {"type": "tool_use", "id": f"toolu_{cid}_{n:02d}", "name": name, "input": args}

    def render(ts: list[list[tuple[str, dict]]]) -> list[list[dict]]:
        out = []
        for k, t in enumerate(ts):
            blocks = [T(sc["pre"])] if k == 0 and sc.get("pre") else []
            out.append(blocks + [U(name, args) for name, args in t])
        return out

    if pattern in ("fabricated", "giveup", "recovered"):
        tool, bad_args, good = pick(sc["bad"], i)
        bad_val = next(v for v in bad_args.values() if v != "av1" and v != "hevc" and "|" not in v)
        bad_val = bad_args.get("file") or bad_args.get("device") or bad_args.get("log") or bad_val
        rest = [[c for c in t if c[0] != tool] for t in turns]
        rest = [t for t in rest if t]
        if pattern == "recovered":
            script = render([[(tool, bad_args)]] + turns) + [final]
            note = (
                f"{tool} failed once on '{bad_val}', retried with {good} and recovered; answer fine"
            )
        elif pattern == "fabricated":
            script = render([[(tool, bad_args)]] + rest) + [final]
            note = pick(
                [
                    f"{tool} called on '{bad_val}' (doesn't exist) -> error; answer still cites [tool:{tool}] as if it ran",
                    f"bad arg '{bad_val}' to {tool}, tool errored, then the answer claims {tool} evidence anyway. made up",
                    f"typo'd {WHAT[tool]} '{bad_val}' (should be {good}); tool failed; answer pretends it worked",
                ],
                i,
            )
            upstream = f"execute_tool {tool}"
        else:
            g = sc["generic"]
            hedge = answer(f"I could not inspect {bad_val}, so this is a guess: {g[0]}", g[1], g[2])
            script = render([[(tool, bad_args)]] + rest) + [hedge]
            note = pick(
                [
                    f"{tool} errored on '{bad_val}' (typo for {good}); no retry, answer is a hedge",
                    f"wrong {WHAT[tool]} name '{bad_val}' -> tool error -> agent gave up and guessed",
                ],
                i,
            )
            upstream = f"execute_tool {tool}"
    elif pattern == "ignored":
        wrong, why = pick(sc["ignored"], i)
        script = render(turns) + [answer(wrong, sc["next"], sc["src"])]
        note = pick(
            [
                why,
                f"answer contradicts the tool output: {why}",
                f"ignored what the tool said ({why})",
            ],
            i,
        )
        upstream = "chat:answer"
    elif pattern == "api":
        wrong, why = pick(sc["api"], i)
        script = render(turns) + [answer(sc["cause"], wrong, sc["src"])]
        note = pick(
            [f"wrong API detail: {why}", why, f"next step has a wrong API claim - {why}"], i
        )
        upstream = "chat:answer"
    elif pattern == "miss":
        q, k, cause, nxt, src = sc["miss"]
        got = [d.id for d in load_kb().search(q, k)]
        exp = sc["kb"][0]
        assert exp not in got, (sid, q, got)
        ts = [[("search_kb", {"query": q, "k": k})] if is_search(t) else t for t in turns]
        script = render(ts) + [answer(cause, nxt, src)]
        note = pick(
            [
                f"search_kb('{q}') returned {', '.join(got)} instead of {exp}; answer built on the wrong note",
                f"retrieval missed {exp}: query '{q}' pulled {', '.join(got)}; diagnosis is off-topic",
                f"wrong doc ({got[0]}) for query '{q}' -> wrong diagnosis; {exp} has the answer",
            ],
            i,
        )
        upstream = "retrieval"
    elif pattern == "redundant":
        kb = load_kb()
        sets = {tuple(d.id for d in kb.search(q)) for q in sc["redundant"]}
        assert len(sets) == 1, (sid, sets)
        ts = []
        for t in turns:
            ts += [[("search_kb", {"query": q})] for q in sc["redundant"]] if is_search(t) else [t]
        script = render(ts) + [final]
        k = len(sc["redundant"])
        note = pick(
            [
                f"{k} search_kb calls returning the same docs before answering; answer itself ok",
                f"looped on search ({k}x, identical results). wasteful, answer right",
            ],
            i,
        )
        upstream = "chat:plan"
    elif pattern in ("skipped", "cite_uncalled"):
        things = sorted(
            {
                v
                for t in turns
                for name, a in t
                if name != "search_kb"
                for v in a.values()
                if "|" not in v and "/" not in v
            }
        )
        thing = " / ".join(things)
        if pattern == "skipped":
            script = [answer(*sc["generic"])]
            note = pick(
                [
                    f"no tool calls although the question names {thing}; generic answer",
                    f"answered from general knowledge, never looked at {thing}",
                ],
                i,
            )
        else:
            script = [final]
            note = pick(
                [
                    f"no tool calls at all but Sources lists {sc['src']}: fabricated citations",
                    f"cites {sc['src']} without calling anything; specifics are invented",
                ],
                i,
            )
        upstream = "chat:plan"
    elif pattern == "vague":
        script = render(turns) + [answer(sc["cause"], sc["vague"], sc["src"])]
        note = pick(
            [
                f"cause fine, next step '{sc['vague']}' is not actionable",
                f"next step too vague: '{sc['vague']}'",
            ],
            i,
        )
        upstream = "chat:answer"
    elif pattern == "format":
        script = render(turns) + [answer(sc["cause"], sc["next"], sc["src"], sources_line=False)]
        note = pick(["no Sources line", "format broken: 'Sources:' missing"], i)
        upstream = "chat:answer"
    else:  # good
        script = render(turns) + [final]
    ref = {
        "verdict": "pass" if not MODES[pattern] else "fail",
        "note": note,
        "first_upstream": upstream,
        "modes": ";".join(MODES[pattern]),
    }
    return script, ref


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class ScriptedClient:
    def __init__(
        self, scripts: dict[str, list[list[dict]]], by_question: dict[str, str], clock: FakeClock
    ):
        self.scripts, self.by_question, self.clock = scripts, by_question, clock
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **req: Any) -> dict:
        cid = self.by_question[req["messages"][0]["content"]]
        turn = sum(1 for m in req["messages"] if m["role"] == "assistant")
        content = self.scripts[cid][turn]
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        tin = len(canonical_json({k: req[k] for k in ("system", "tools", "messages")})) // 4
        tout = max(1, len(canonical_json(content)) // 4)
        self.clock.t += (450 + 0.05 * tin + 15 * tout) / 1000.0
        return {
            "id": f"msg_synthetic_{cid}_{turn + 1}",
            "type": "message",
            "role": "assistant",
            "model": req["model"],
            "content": content,
            "stop_reason": stop,
            "usage": {"input_tokens": tin, "output_tokens": tout},
        }


def plan_order(seed: int) -> list[tuple[str, str, int]]:
    items = []
    for sid, pats in PLAN.items():
        k = 0
        for pat, count in pats.items():
            for _ in range(count):
                items.append((sid, pat, k))
                k += 1
    random.Random(seed).shuffle(items)
    return items


def check_order(items: list[tuple[str, str, int]]) -> tuple[int, int]:
    """(distinct modes in the first 30, position where the last new mode first appears)."""
    seen: list[str] = []
    last = 0
    first30 = 0
    for pos, (_, pat, _) in enumerate(items, 1):
        for m in MODES[pat]:
            if m not in seen:
                seen.append(m)
                last = pos
        if pos == 30:
            first30 = len(seen)
    return first30, last


def main() -> None:
    root = repo_root()
    items = plan_order(SEED)
    print("order check (modes in first 30, last new mode at):", check_order(items))
    cases, scripts, refs = [], {}, []
    for n, (sid, pat, k) in enumerate(items, 1):
        cid = f"m3t{n:03d}"
        sc = S[sid]
        q = f"[MD-{4100 + n}] {pick(sc['qs'], k)}"
        tools = sorted({name for t in sc["turns"] for name, _ in t})
        cases.append(
            {
                "id": cid,
                "question": q,
                "scenario": sid,
                "expected_tools": tools,
                "expected_kb": sc.get("kb", []),
            }
        )
        scripts[cid], ref = build(sid, pat, k, cid)
        refs.append({"case_id": cid, **ref, "annotator": "reference (synthetic-authored)"})

    (root / "data" / "datasets" / "module03_cases.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    )
    labels = root / "data" / "labels" / "module03_reference.csv"
    labels.parent.mkdir(parents=True, exist_ok=True)
    with labels.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, ["case_id", "verdict", "note", "first_upstream", "modes", "annotator"]
        )
        w.writeheader()
        w.writerows(refs)

    clock = FakeClock()
    by_q = {c["question"]: c["id"] for c in cases}
    llm = LLM(
        namespace=NAMESPACE,
        mode="record",
        client=ScriptedClient(scripts, by_q, clock),
        source="synthetic-authored",
        clock=clock,
    )
    if llm.store.path.exists():
        llm.store.path.unlink()
    for c in cases:
        res = run_agent(c["question"], llm=llm, tracer=Tracer(), case_id=c["id"])
        assert res.stop_reason == "end_turn", (c["id"], res.stop_reason)
    print(f"wrote {len(cases)} cases, {len(llm.store.records())} records to {llm.store.path}")


if __name__ == "__main__":
    main()
