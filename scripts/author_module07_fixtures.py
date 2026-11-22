"""Write the module 7 fixtures and labels. No API key was used to write the course.

Every model output below is answered by a scripted client and recorded through the lab's real code
paths (rag_request, chat.run_session, multiagent.run_team, vision requests, run_judge), so replay
keys match exactly. Every record is tagged "source": "synthetic-authored". The behaviour of each
run is chosen here, deterministically, and written to the label files as the reference truth:

    data/labels/module07_rag.csv        per (system, query): correct, faithful, relevant
    data/labels/module07_sessions.csv   per chat session: resolved, gave up early, retention, ...
    data/labels/module07_agents.csv     per multi-agent run: reference route and tools, verdict

Behaviour mixes, in short:
- RAG: when the context holds an answering passage, most answers are right; some add an unsupported
  claim, answer from a distractor passage, or cite an id that was not in the context. When it does
  not, the model either abstains or answers from general knowledge (unfaithful). The draw is the
  same for both retrieval systems, so differences between them come from retrieval.
- Chat: prompt v1 answers at once (assumes, or gives up); v2 asks first, with planted retention
  failures, needless questions, a give-up after asking, and two simulated-user faults.
- Multi-agent: correct runs plus wrong routes, briefs that drop names, bad tool arguments (some
  recovered), and answers that ignore the findings.
- Vision: judges catch severe artifacts and miss some mild ones, with one false alarm each.
- Judges: verdict = label, except documented, deterministic errors (see each section).

Usage:  uv run python scripts/author_module07_fixtures.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from author_module03_fixtures import FakeClock  # noqa: E402
from module03_scenarios import S  # noqa: E402

from evalkit import LLM, repo_root  # noqa: E402
from evalkit.fixtures import canonical_json  # noqa: E402
from evalkit.judge import Item, run_judge  # noqa: E402
from mediadoctor import chat, lab04, lab05, lab07, multiagent, rag, vision  # noqa: E402
from mediadoctor.tools import ToolError, run_tool  # noqa: E402

SRC = "synthetic-authored"
LABELS = repo_root() / "data" / "labels"
REC = repo_root() / "fixtures" / "recorded"


def _u(*parts: Any) -> float:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:12], 16) / 16**12


def T(text: str) -> dict:
    return {"type": "text", "text": text}


class FnClient:
    """Answers each request with fn(request) -> content blocks (or a string)."""

    def __init__(self, fn: Callable[[dict[str, Any]], Any], clock: FakeClock):
        self.fn, self.clock, self.n = fn, clock, 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **req: Any) -> dict[str, Any]:
        out = self.fn(req)
        content = [T(out)] if isinstance(out, str) else out
        self.n += 1
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        tin = len(canonical_json(req)) // 4
        tout = max(1, len(canonical_json(content)) // 4)
        self.clock.t += (400 + 0.04 * tin + 14 * tout) / 1000.0
        return {
            "id": f"msg_synthetic_{hashlib.sha256(canonical_json(content).encode()).hexdigest()[:12]}_{self.n}",
            "type": "message",
            "role": "assistant",
            "model": req["model"],
            "content": content,
            "stop_reason": stop,
            "usage": {"input_tokens": tin, "output_tokens": tout},
        }


def recorder(namespace: str, fn: Callable[[dict[str, Any]], Any]) -> LLM:
    clock = FakeClock()
    return LLM(
        namespace=namespace, mode="record", client=FnClient(fn, clock), source=SRC, clock=clock
    )


def verdict_json(critique: str, passed: bool) -> str:
    return json.dumps({"critique": critique, "verdict": "PASS" if passed else "FAIL"})


def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    with (LABELS / name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def sentences(text: str, n: int = 2) -> str:
    return " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:n])


# --- A. RAG ------------------------------------------------------------------------------------------

INVENTED = [
    "This behaviour was introduced in Android 9 (API 28).",
    "Restarting the device clears the condition permanently.",
    "Most devices allow up to 16 such instances at once.",
    'The fix is to set android:hardwareAccelerated="false" in the manifest.',
    "ExoPlayer handles this automatically since version 2.5.",
]
GUESS = {
    "codec": "This is usually a bug in the device's codec driver; updating the firmware fixes it.",
    "streaming": "This is usually a CDN caching problem; purging the cache fixes it.",
    "audio": "This is usually caused by the Bluetooth stack; re-pairing the device fixes it.",
    "video": "This is usually caused by the GPU driver; disabling hardware overlays fixes it.",
}
ABSTAIN = "Answer: The passages do not cover this question, so I cannot answer it from the knowledge base.\nSources: none"


def rag_behaviour(q: rag.Query, hit: bool) -> str:
    if hit:
        u = _u("rag-hit", q.id)
        return (
            "good"
            if u < 0.70
            else "unfaithful"
            if u < 0.82
            else "distractor"
            if u < 0.90
            else "bad_cite"
        )
    u = _u("rag-miss", q.id)
    return "abstain" if u < 0.45 else "hallucinate" if u < 0.88 else "lucky"


def rag_answer(q: rag.Query, ctx: list[rag.Chunk], beh: str) -> tuple[str, str]:
    """(answer text, the behaviour actually used)."""
    sec = rag.sections()
    ans_chunk = next((c for c in ctx if c.section in q.answering), None)
    if beh in ("good", "unfaithful", "bad_cite", "distractor") and ans_chunk is None:
        beh = "abstain"
    if beh == "distractor":
        other = next((c for c in ctx if c.section not in q.relevant), None)
        if other is None:
            beh = "good"
        else:
            return f"Answer: {sentences(sec[other.section].text)}\nSources: [kb:{other.id}]", beh
    if beh in ("good", "unfaithful", "bad_cite"):
        body = sentences(sec[ans_chunk.section].text)
        if beh == "unfaithful":
            body += " " + INVENTED[int(_u("inv", q.id) * len(INVENTED))]
        cite = f"[kb:{ans_chunk.doc}]" if beh == "bad_cite" else f"[kb:{ans_chunk.id}]"
        return f"Answer: {body}\nSources: {cite}", beh
    if beh == "abstain":
        return ABSTAIN, beh
    first = f"[kb:{ctx[0].id}]" if ctx else "none"
    if beh == "lucky":
        best = sorted(q.answering)[0]
        return f"Answer: {sentences(sec[best].text)}\nSources: {first}", beh
    return f"Answer: {GUESS[q.topic]}\nSources: {first}", beh


RAG_LABELS = {  # behaviour -> (correct, faithful, relevant)
    "good": (1, 1, 1), "unfaithful": (0, 0, 1), "distractor": (0, 1, 0), "bad_cite": (1, 1, 1),
    "abstain": (0, 1, 0), "hallucinate": (0, 0, 1), "lucky": (1, 0, 1),
}  # fmt: skip
RAG_NOTES = {
    "good": "answers from the retrieved passage",
    "unfaithful": "correct core, plus a specific claim the passages do not contain",
    "distractor": "answers from an unrelated passage in the context",
    "bad_cite": "correct and grounded, but cites an id that is not in the context",
    "abstain": "says the passages do not cover it",
    "hallucinate": "answers from general knowledge (wrong) and cites an unrelated passage",
    "lucky": "right answer, but not from the passages (none of them answer it)",
}


def write_rag() -> None:
    table: dict[str, str] = {}
    rows, runs = [], []
    for system in rag.SYSTEMS:
        for q in rag.queries():
            ctx = rag.context_for(q.text, system)
            hit = any(c.section in q.answering for c in ctx)
            text, beh = rag_answer(q, ctx, rag_behaviour(q, hit))
            req = rag.rag_request(q.text, ctx)
            table[req["messages"][0]["content"]] = text
            c, f, r = RAG_LABELS[beh]
            rows.append({"system": system, "query_id": q.id, "retrieval_hit": "yes" if hit else "no",
                         "correct": "yes" if c else "no", "faithful": "yes" if f else "no",
                         "relevant": "yes" if r else "no", "note": RAG_NOTES[beh],
                         "annotator": f"reference ({SRC})"})  # fmt: skip
            runs.append((lab07.RagRun(system, q, tuple(ctx), text), beh))
    llm = recorder(lab07.RAG_NAMESPACE, lambda req: table[req["messages"][0]["content"]])
    for system in rag.SYSTEMS:
        for q in rag.queries():
            ctx = rag.context_for(q.text, system)
            llm.create(**rag.rag_request(q.text, ctx))
    write_csv("module07_rag.csv", rows)

    # Judges. Faithfulness misses a quarter of the subtle invented claims and half of the "lucky"
    # answers (true in general, so they read as fine); 5% false alarms. Relevance: 5% flips.
    verdicts: dict[tuple[str, str], str] = {}
    for run, beh in runs:
        c, f, r = RAG_LABELS[beh]
        u = _u("faith", run.query.id, beh)
        fp = bool(f) if u >= 0.05 else not f
        if beh == "unfaithful" and u < 0.25:
            fp = True
        if beh == "lucky" and u < 0.5:
            fp = True
        if fp:
            crit = "Every statement in the answer appears in the search_kb passages."
        elif beh == "unfaithful":
            crit = f'The answer adds "{run.answer.split(". ")[-1].split(chr(10))[0][:90]}", which no passage states.'
        else:
            crit = "The answer's main claim is not in any of the passages; it comes from outside the context."
        verdicts[("faithfulness", run.id)] = verdict_json(crit, fp)
        rp = bool(r) if _u("rel", run.query.id, beh) >= 0.08 else not r
        crit = ("The answer responds to the question that was asked." if rp
                else "The answer does not address the question: it declines or talks about another topic.")  # fmt: skip
        verdicts[("answer-relevance", run.id)] = verdict_json(crit, rp)
    items = [r.item() for r, _ in runs]
    for name in ("faithfulness", "answer-relevance"):
        sp = lab07.spec(name)
        by_text = {json.dumps(build_key(sp, it)): verdicts[(name, it.case_id)] for it in items}
        llm = recorder(lab07.JUDGE_NAMESPACE, lambda req, bt=by_text: bt[json.dumps(key_of(req))])
        run_judge(llm.create, sp, items, {}, lambda resp: resp["content"][0]["text"])


def build_key(sp: Any, it: Item) -> list[str]:
    from evalkit.judge import build_judge_request

    return key_of(build_judge_request(sp, it, {}))


def key_of(req: dict[str, Any]) -> list[str]:
    return [req["system"], req["messages"][0]["content"]]


# --- B. Chat -------------------------------------------------------------------------------------------

Q = {
    "clip": "Question: What codec, resolution and frame rate is the clip?",
    "decoders": "Question: Which decoders does MediaCodecList show for it on that phone?",
    "layout": "Question: What top-level boxes does ffprobe show for one of the files, in order?",
    "offset": "Question: What start times does ffprobe report for the audio and video streams?",
    "display": "Question: Does the phone's display report HDR support (Display.getHdrCapabilities())?",
    "log": "Question: What error does logcat show when it fails?",
    "code": "Question: How does the app create and release its decoders?",
    "level": "Question: What Widevine security level does MediaDrm report on those phones?",
    "encode": "Question: What are the encoding settings (bit depth and bitrate)?",
}
REASK = {"offset": "Question: Just to confirm, what start times do the two streams have?"}
GIVE_UP = {
    1: "Likely cause: I can't tell what is wrong from this description alone.\n"
       "Next step: Contact the device manufacturer's developer support with a bug report.",
    2: "Likely cause: Hard to say without a full bug report.\n"
       "Next step: Capture a bug report and file it with the device vendor.",
    3: "Likely cause: Video quality problems have many possible causes.\n"
       "Next step: Ask your encoding vendor to review the stream.",
}  # fmt: skip
WRONG = {
    "c01": "Likely cause: Hard to say for sure, but network throughput is probably too low for the 4K stream, so the player rebuffers.\n"
           "Next step: Check the bandwidth estimate and lower the starting bitrate.",
    "c05": "Likely cause: The audio track drifts because the clip has a variable frame rate.\n"
           "Next step: Re-encode at a constant frame rate.",
    "c07": "Likely cause: A memory leak in the thumbnail bitmap cache.\n"
           "Next step: Profile the heap with Android Studio's memory profiler.",
    "c13": "Likely cause: Since the decoder supports these clips, the files themselves are probably corrupt.\n"
           "Next step: Validate the clips with ffprobe, and if it persists, contact the device vendor.",
}  # fmt: skip
DRIFT = {"c13": "It supports everything we've tried, Main10 included, as far as I know."}

B1 = {"c01": "assume", "c03": "ask_all", "c05": "assume", "c06": "giveup", "c07": "assume",
      "c09": "ask_all", "c10": "giveup", "c11": "giveup", "c13": "giveup", "c15": "good",
      "c16": "good"}  # fmt: skip
B2 = {"c01": "ask", "c03": "ask", "c05": "reask", "c06": "ask_giveup", "c07": "ask_leak",
      "c09": "ask", "c10": "ask", "c11": "giveup", "c13": "ask_drift", "c15": "ask",
      "c16": "giveup3", "c04": "needless", "c12": "needless"}  # fmt: skip
# Gave-up-early judge errors: misses the polite give-up after a question (c06-v2), and flags two
# hedged answers that did not give up (c01-v1 "hard to say for sure", c13-v2 "contact the vendor").
GAVE_UP_JUDGE_FLIPS = {"c06-v2", "c01-v1", "c13-v2"}


def good(sc: chat.Scenario) -> str:
    return f"Likely cause: {sc.cause}\nNext step: {sc.next}"


def plan(sc: chat.Scenario, prompt: str) -> tuple[list[str], list[str], dict[str, str]]:
    beh = (B1 if prompt == "v1" else B2).get(sc.id, "good")
    a: list[str] = []
    u: list[str] = []
    lab = {"resolved": "yes", "gave_up_early": "no", "re_ask": "no", "needless_question": "no",
           "simulator_issue": "", "note": ""}  # fmt: skip
    miss = list(sc.missing)
    if beh == "good":
        a = [good(sc)]
        lab["note"] = (
            "diagnosed from the opening" if not miss else "diagnosed without asking (a lucky guess)"
        )
    elif beh == "assume":
        a = [WRONG[sc.id]]
        lab.update(resolved="no", note="assumed instead of asking; wrong cause")
    elif beh in ("giveup", "giveup3"):
        a = [GIVE_UP[3 if beh == "giveup3" else 1]]
        lab.update(
            resolved="no",
            gave_up_early="yes",
            note="gave up at once; one question would have unlocked it",
        )
    elif beh == "ask_all":
        a = [
            " ".join(
                Q[f] if i == 0 else Q[f].removeprefix("Question: ") for i, f in enumerate(miss)
            ),
            good(sc),
        ]
        u = [" ".join(sc.facts[f] for f in miss)]
        lab["note"] = "asked once, then diagnosed"
    elif beh == "ask":
        a = [Q[f] for f in miss] + [good(sc)]
        u = [sc.facts[f] for f in miss]
        lab["note"] = "asked for each missing fact, then diagnosed"
    elif beh == "reask":
        f = miss[0]
        a, u = [Q[f], REASK[f], good(sc)], [sc.facts[f], "As I said: " + sc.facts[f]]
        lab.update(re_ask="yes", note="asked again for a fact the user had just given")
    elif beh == "ask_giveup":
        f = miss[0]
        a, u = [Q[f], GIVE_UP[2]], [sc.facts[f]]
        lab.update(resolved="no", gave_up_early="yes", note="asked, got the fact, then gave up")
    elif beh == "ask_leak":
        a, u = [Q[miss[0]], good(sc)], [" ".join(sc.facts[f] for f in miss)]
        lab.update(simulator_issue="volunteered a fact that was not asked for",
                   note="the simulated user leaked the second fact, so the agent never had to ask")  # fmt: skip
    elif beh == "ask_drift":
        f = miss[0]
        a, u = [Q[f], WRONG[sc.id]], [DRIFT[sc.id]]
        lab.update(resolved="no", simulator_issue="contradicted its own facts",
                   note="the simulated user gave a wrong fact; the agent's wrong answer follows from it")  # fmt: skip
    elif beh == "needless":
        f = sc.given[0]
        a, u = [Q[f], good(sc)], ["As I said: " + sc.facts[f]]
        lab.update(
            re_ask="yes", needless_question="yes", note="asked for a fact already in the opening"
        )
    else:
        raise ValueError(beh)
    return a, u, lab


def write_chat() -> None:
    current: dict[str, Any] = {}

    def agent_fn(req: dict[str, Any]) -> str:
        n = sum(1 for m in req["messages"] if m["role"] == "assistant")
        return current["agent"][n]

    def user_fn(req: dict[str, Any]) -> str:
        n = req["messages"][0]["content"].count("\n\nMediaDoctor: ") - 1
        return current["user"][n]

    agent = recorder(chat.AGENT_NAMESPACE, agent_fn)
    user = recorder(chat.USER_NAMESPACE, user_fn)
    rows, sessions = [], {}
    for prompt in chat.CHAT_PROMPTS:
        for sc in chat.scenarios().values():
            a, u, lab = plan(sc, prompt)
            current.update(agent=a, user=u)
            s = chat.run_session(sc, prompt, agent, user)
            assert s.agent_turns == a and s.user_turns[1:] == u, s.id
            sessions[s.id] = s
            rows.append({"session_id": s.id, **lab, "annotator": f"reference ({SRC})"})
    write_csv("module07_sessions.csv", rows)

    labels = {r["session_id"]: r for r in rows}
    sp = lab07.spec("gave-up-early")
    items = [
        Item(s.id, chat.scenarios()[s.scenario].opening, s.transcript()) for s in sessions.values()
    ]
    table = {}
    for it in items:
        gave_up = labels[it.case_id]["gave_up_early"] == "yes"
        passed = (not gave_up) ^ (it.case_id in GAVE_UP_JUDGE_FLIPS)
        last = sessions[it.case_id].agent_turns[-1].replace("\n", " ")
        crit = (f'MediaDoctor ends with "{last[:110]}" without asking the user for the missing detail.'
                if not passed else
                f'MediaDoctor keeps working: its last turn is "{last[:110]}".')  # fmt: skip
        table[json.dumps(build_key(sp, it))] = verdict_json(crit, passed)
    llm = recorder(lab07.JUDGE_NAMESPACE, lambda req: table[json.dumps(key_of(req))])
    run_judge(llm.create, sp, items, {}, lambda resp: resp["content"][0]["text"])


# --- C. Multi-agent ------------------------------------------------------------------------------------

OWNER = {"ffprobe": "media", "codec_caps": "device", "logcat_grep": "device"}
CYCLE = ["good", "lost", "devname", "misroute", "good", "ignored", "devname_fix", "lost", "good",
         "misroute", "stuck", "devname", "good", "bad_args", "ignored", "devname"]  # fmt: skip
PRETTY = {
    "lumen-l3": "Lumen L3",
    "atlas-a1": "Atlas A1",
}  # how the device specialist "likes" to write names
GUESS_ARGS = {
    "ffprobe": lambda a: {"file": "video.mp4"},
    "codec_caps": lambda a: {**a, "device": "the user's phone"},
    "logcat_grep": lambda a: {**a, "log": "logcat.txt"},
}
WRONG_ROUTE = {("media", "device"): ["device"], ("media",): ["knowledge"], ("device",): ["media"]}


def expected(sid: str) -> tuple[list[str], list[tuple[str, dict]]]:
    calls = [c for turn in S[sid]["turns"] for c in turn]
    route = [r for r in ("media", "device") if any(OWNER.get(n) == r for n, _ in calls)] or [
        "knowledge"
    ]
    ordered = [c for r in route for c in calls if OWNER.get(c[0]) == r]
    ordered += [c for c in calls if c[0] == "search_kb"]
    return route, ordered


def tool_use(cid: str, n: int, name: str, args: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_{cid}_{n}", "name": name, "input": args}


def owner_of(name: str, route: list[str]) -> str | None:
    if name == "search_kb":
        return route[-1]
    o = OWNER[name]
    return o if o in route else None


def summarize(name: str, args: dict) -> str:
    try:
        out = run_tool(name, args)
    except ToolError as exc:
        return f"{name} failed: {exc}"
    return f"{name} {json.dumps(args)} returned {' '.join(out.split())[:180]}"


def team_script(row: dict[str, Any], beh: str) -> tuple[list[list[dict]], str, str]:
    """(responses in call order, verdict, note)."""
    sid = lab04.scenario_for(row)
    sc = S[sid]
    route, calls = expected(sid)
    cid, q = row["id"], row["question"]
    names = lab07.entities(q)
    bad = {b[0]: b[1] for b in sc.get("bad", [])}
    if beh in ("devname", "devname_fix"):
        bad = {n: {**a, "device": PRETTY[a["device"]]} for n, a in calls if n == "codec_caps"}
        if not bad:
            beh = "good"
    if beh in ("lost", "stuck") and not names:
        beh = "good"
    if beh == "misroute" and tuple(route) not in WRONG_ROUTE:
        beh = "good"
    if beh in ("bad_args", "stuck") and not any(n in bad for n, _ in calls):
        beh = "lost" if beh == "stuck" and names else "good"
    retry = beh in ("bad_args", "devname_fix")
    used_route = WRONG_ROUTE[tuple(route)] if beh == "misroute" else route
    brief = ("The user reports a playback problem; please investigate it." if beh == "lost"
             else f"The user asks: {q}")  # fmt: skip
    out: list[list[dict]] = [[T(json.dumps({"route": used_route, "brief": brief}))]]
    n = 0
    evidence_ok = True
    bad_done = False
    for spec_name in used_route:
        mine = [(nm, a) for nm, a in calls if owner_of(nm, used_route) == spec_name]
        if beh == "misroute" and not mine:
            mine = [("search_kb", {"query": q})]
        if beh == "lost":
            mine = [(nm, GUESS_ARGS[nm](a) if nm in GUESS_ARGS else a) for nm, a in mine]
        if (
            beh in ("bad_args", "stuck", "devname", "devname_fix")
            and not bad_done
            and any(nm in bad for nm, _ in mine)
        ):
            first = [(nm, bad[nm] if nm in bad else a) for nm, a in mine]
            blocks = []
            for nm, a in first:
                n += 1
                blocks.append(tool_use(cid, n, nm, a))
            out.append(blocks)
            bad_done = True
            if not retry:
                out.append(
                    [T("Findings: The tool call failed, so there is no evidence to report.")]
                )
                evidence_ok = False
                continue
            retry = [(nm, a) for nm, a in mine if nm in bad]
            blocks = []
            for nm, a in retry:
                n += 1
                blocks.append(tool_use(cid, n, nm, a))
            out.append(blocks)
        else:
            blocks = []
            for nm, a in mine:
                n += 1
                blocks.append(tool_use(cid, n, nm, a))
            out.append(blocks)
        if beh == "lost":
            out.append(
                [
                    T(
                        "Findings: I could not inspect anything: the brief names no file, device, or log, and my guesses failed."
                    )
                ]
            )
            evidence_ok = False
        else:
            out.append([T("Findings: " + "; ".join(summarize(nm, a) for nm, a in mine))])
    if beh == "misroute":
        evidence_ok = False
    # Without an "ignored" text for the scenario, the planted answer failure is a generic answer.
    generic = not evidence_ok or (beh == "ignored" and not sc.get("ignored"))
    gen = sc.get("generic") or (
        "The problem could have several causes.",
        "Check the app's logs.",
        "none",
    )
    if generic:
        answer = f"Likely cause: {gen[0]}\nNext step: {gen[1]}\nSources: {gen[2]}"
    elif beh == "ignored" and sc.get("ignored"):
        answer = (
            f"Likely cause: {sc['ignored'][0][0]}\nNext step: {sc['next']}\nSources: {sc['src']}"
        )
    else:
        answer = f"Likely cause: {sc['cause']}\nNext step: {sc['next']}\nSources: {sc['src']}"
    out.append([T(answer)])
    verdict = "pass" if beh in ("good", "bad_args", "devname_fix") else "fail"
    note = {
        "good": "correct route, complete brief, correct answer",
        "bad_args": "a bad tool argument, recovered on retry",
        "lost": "the brief dropped the file/device/log names; the specialist guessed and failed",
        "stuck": "a bad tool argument and no retry; no evidence",
        "devname": "the device specialist wrote the device's display name; codec_caps failed; no retry",
        "devname_fix": "the device specialist wrote the display name, then retried with the id",
        "misroute": f"routed to {'+'.join(used_route)} instead of {'+'.join(route)}",
        "ignored": "evidence gathered, but the answer contradicts it"
        if sc.get("ignored")
        else "evidence gathered, but the answer is generic",
    }[beh]
    return out, verdict, note


def write_agents() -> None:
    rows = [
        r
        for r in lab05.label_rows()
        if r["split"] in ("dev", "test") and r["ambiguity"] != "missing-detail"
    ]
    queue: list[list[dict]] = []
    llm = recorder(multiagent.NAMESPACE, lambda req: queue.pop(0))
    refs = []
    for i, r in enumerate(rows):
        script, verdict, note = team_script(r, CYCLE[i % len(CYCLE)])
        queue[:] = script
        multiagent.run_team(r["question"], r["id"], llm)
        assert not queue, r["id"]
        route, calls = expected(lab04.scenario_for(r))
        refs.append({"case_id": r["id"], "split": r["split"], "scenario": lab04.scenario_for(r),
                     "expected_route": ";".join(route),
                     "expected_tools": ";".join(dict.fromkeys(n for n, _ in calls)),
                     "verdict": verdict, "note": note, "annotator": f"reference ({SRC})"})  # fmt: skip
    write_csv("module07_agents.csv", refs)


# --- D. Vision ------------------------------------------------------------------------------------------

FLAGGED = {  # frames each judge calls FAIL (artifact present)
    "frame-blocking": {"blocking_severe_testsrc.png", "blocking_severe_mandelbrot.png",
                       "blocking_severe_gradient.png", "blocking_mild_gradient.png",
                       "banding_severe_b.png"},
    "frame-banding": {"banding_severe_a.png", "banding_severe_b.png", "banding_severe_c.png",
                      "banding_mild_c.png", "blocking_severe_gradient.png"},
}  # fmt: skip
SPECTRO = {
    "spec_clean_440.png": (
        "none",
        "A single steady line at the tone's frequency, with nothing above it.",
    ),
    "spec_clean_1000.png": (
        "none",
        "One clean horizontal line for the whole clip; no gaps or harmonics.",
    ),
    "spec_dropout_440.png": (
        "dropout",
        "The tone disappears completely for a stretch in the middle: a dark vertical gap.",
    ),
    "spec_dropout_1000.png": ("none", "A continuous tone; I see no gap or added energy."),
    "spec_clipping_440.png": (
        "clipping",
        "Bright evenly spaced harmonics fill the spectrum above the fundamental, typical of hard clipping.",
    ),
    "spec_clipping_1000.png": (
        "noise",
        "Faint energy is spread across many frequencies above the tone, like broadband noise.",
    ),
}


def write_vision() -> None:
    table = {}
    for name, flagged in FLAGGED.items():
        sp = lab07.spec(name)
        for img in vision.images().values():
            if img.kind != "frame":
                continue
            bad = img.name in flagged
            what = name.removeprefix("frame-")
            crit = (f"Visible {what}: flat-coloured regions with hard edges that are not part of the content." if bad
                    else f"No {what}: edges and gradients look continuous; the sharp edges belong to the pattern.")  # fmt: skip
            req = vision.judge_request(sp, img.name)
            table[
                json.dumps([req["system"], req["messages"][0]["content"][0]["source"]["data"]])
            ] = verdict_json(crit, not bad)
    for img_name, (defect, ev) in SPECTRO.items():
        req = vision.spectrogram_request(img_name)
        table[json.dumps([req["system"], req["messages"][0]["content"][0]["source"]["data"]])] = (
            f"Defect: {defect}\nEvidence: {ev}"
        )

    def fn(req: dict[str, Any]) -> str:
        return table[
            json.dumps([req["system"], req["messages"][0]["content"][0]["source"]["data"]])
        ]

    llm = recorder(vision.NAMESPACE, fn)
    for name in FLAGGED:
        sp = lab07.spec(name)
        for img in vision.images().values():
            if img.kind == "frame":
                llm.create(**vision.judge_request(sp, img.name))
    for img_name in SPECTRO:
        llm.create(**vision.spectrogram_request(img_name))


def main() -> None:
    for p in REC.glob("mediadoctor-m7-*.jsonl"):
        p.unlink()
    write_rag()
    write_chat()
    write_agents()
    write_vision()
    for p in sorted(REC.glob("mediadoctor-m7-*.jsonl")):
        n = sum(1 for _ in p.open(encoding="utf-8"))
        print(f"{p.relative_to(repo_root())}: {n} records, {p.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
