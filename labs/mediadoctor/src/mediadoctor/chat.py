"""Multi-turn MediaDoctor chat with a simulated user (module 7).

The chat agent has no tools: it diagnoses from what the user tells it, so it must ask for missing
details. The simulated user is a second model that plays an engineer who knows some facts
(`facts`) and reveals each one only when asked. A session is at most MAX_USER_TURNS user messages:

    user (opening, fixed text) -> agent -> user (simulated) -> agent -> user (simulated) -> agent

An agent turn is either a question ("Question: ...") or a final answer ("Likely cause: ... /
Next step: ..."). The session ends at the first final answer or when the user turns run out.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from evalkit import LLM, load_models, repo_root, text_of

AGENT_NAMESPACE = "mediadoctor-m7-chat"
USER_NAMESPACE = "mediadoctor-m7-users"
MAX_USER_TURNS = 3

CHAT_V1 = """\
You are MediaDoctor, an assistant for Android and multimedia engineers, in a chat with an engineer.
You have no tools: work from what the user tells you.

Reply in exactly this format:
Likely cause: <one or two sentences>
Next step: <the single most useful thing to check or change>"""

CHAT_V2 = """\
You are MediaDoctor, an assistant for Android and multimedia engineers, in a chat with an engineer.
You have no tools: work from what the user tells you.

If a diagnosis depends on a detail the user has not given (the clip's format, what the device
supports, a log line, how the code behaves), ask for it first, in one short message that starts
with "Question:". Never ask for something the user has already told you.

When you can diagnose, reply in exactly this format:
Likely cause: <one or two sentences>
Next step: <the single most useful thing to check or change>"""

CHAT_PROMPTS = {"v1": CHAT_V1, "v2": CHAT_V2}

USER_SYSTEM = """\
You are role-playing an Android engineer who asked a support assistant for help. Stay in character.

Your problem, in your own words: {opening}

What you know (reveal a fact only when the assistant asks for it, in your own words, briefly):
{facts}

Rules: answer only what was asked; never volunteer other facts; never invent details that are
not listed; if you do not know, say so. Reply with your next chat message only."""

# Words that show an agent question asks for a given kind of fact. Used by the turn-level checks.
FACT_TERMS = {
    "clip": r"\bcodec\b|resolution|frame rate|\bformat\b|\bclip\b|\bfile\b",
    "decoders": r"decoder|MediaCodecList|hardware|supports?",
    "layout": r"\bbox|moov|layout|faststart|structure|ffprobe",
    "offset": r"start time|offset|timestamp|pts|ffprobe",
    "display": r"display|screen|HDR support|getHdrCapabilities",
    "log": r"\blogs?\b|logcat|error|exception|stack",
    "code": r"\bcode\b|release|lifecycle|audio focus|how (do|does) (you|your|the app)",
    "level": r"widevine|security level|\bL1\b|\bL3\b|MediaDrm",
    "encode": r"encod|bitrate|bit depth|settings",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    opening: str
    facts: dict[str, str]
    given: tuple[str, ...]
    needed: tuple[str, ...]
    cause: str
    next: str
    cause_terms: str

    @property
    def missing(self) -> tuple[str, ...]:
        """Facts a diagnosis needs that the opening does not give: the agent should ask."""
        return tuple(f for f in self.needed if f not in self.given)


def scenarios_path() -> Path:
    return repo_root() / "data" / "sessions" / "module07_chat.json"


@cache
def scenarios() -> dict[str, Scenario]:
    raw = json.loads(scenarios_path().read_text(encoding="utf-8"))["sessions"]
    out = {}
    for s in raw:
        sc = Scenario(
            s["id"], s["title"], s["opening"], dict(s["facts"]), tuple(s["given"]),
            tuple(s["needed"]), s["cause"], s["next"], s["cause_terms"],
        )  # fmt: skip
        unknown = (set(sc.given) | set(sc.needed)) - set(sc.facts) | set(sc.facts) - set(FACT_TERMS)
        if unknown:
            raise ValueError(f"{sc.id}: unknown facts {sorted(unknown)}")
        out[sc.id] = sc
    return out


def asked_facts(text: str) -> set[str]:
    """Which kinds of fact an agent question asks for (keyword match on FACT_TERMS)."""
    return {k for k, rx in FACT_TERMS.items() if re.search(rx, text, re.I)}


def is_question(text: str) -> bool:
    return text.lstrip().startswith("Question:")


def is_final(text: str) -> bool:
    return "Likely cause:" in text


@dataclass
class Session:
    id: str  # <scenario>-<prompt version>
    scenario: str
    prompt: str
    turns: list[tuple[str, str]] = field(default_factory=list)  # (role, text), role user|agent

    @property
    def agent_turns(self) -> list[str]:
        return [t for r, t in self.turns if r == "agent"]

    @property
    def user_turns(self) -> list[str]:
        return [t for r, t in self.turns if r == "user"]

    @property
    def final(self) -> str:
        last = self.agent_turns[-1] if self.agent_turns else ""
        return last if is_final(last) else ""

    def transcript(self) -> str:
        names = {"user": "User", "agent": "MediaDoctor"}
        return "\n\n".join(f"{names[r]}: {t}" for r, t in self.turns)


def agent_request(messages: list[dict[str, str]], prompt: str) -> dict[str, Any]:
    role = load_models()["agent"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": CHAT_PROMPTS[prompt],
        "messages": [dict(m) for m in messages],
    }


def user_request(sc: Scenario, session: Session) -> dict[str, Any]:
    role = load_models()["synth"]
    facts = "\n".join(f"- {v}" for v in sc.facts.values())
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": USER_SYSTEM.format(opening=sc.opening, facts=facts),
        "messages": [
            {
                "role": "user",
                "content": "The conversation so far:\n\n"
                + session.transcript()
                + "\n\nWrite your next message to MediaDoctor.",
            }
        ],
    }


def run_session(
    sc: Scenario, prompt: str, agent: LLM | None = None, user: LLM | None = None
) -> Session:
    agent = agent or LLM(namespace=AGENT_NAMESPACE)
    user = user or LLM(namespace=USER_NAMESPACE)
    s = Session(f"{sc.id}-{prompt}", sc.id, prompt, [("user", sc.opening)])
    messages = [{"role": "user", "content": sc.opening}]
    while True:
        reply = text_of(agent.create(**agent_request(messages, prompt))).strip()
        s.turns.append(("agent", reply))
        messages.append({"role": "assistant", "content": reply})
        if is_final(reply) or len(s.user_turns) >= MAX_USER_TURNS:
            return s
        said = text_of(user.create(**user_request(sc, s))).strip()
        s.turns.append(("user", said))
        messages.append({"role": "user", "content": said})


def run_sessions(agent: LLM | None = None, user: LLM | None = None) -> dict[str, Session]:
    out = {}
    for prompt in CHAT_PROMPTS:
        for sc in scenarios().values():
            s = run_session(sc, prompt, agent, user)
            out[s.id] = s
    return out


# --- Turn-level and session-level code checks -------------------------------------------------------


def known_before(sc: Scenario, s: Session, agent_index: int) -> set[str]:
    """Facts the user had already given before the agent's turn number `agent_index`."""
    known = set(sc.given)
    seen_agent = 0
    for role, text in s.turns:
        if role == "agent":
            if seen_agent == agent_index:
                break
            seen_agent += 1
        elif text != sc.opening:
            known |= {k for k, v in sc.facts.items() if _mentions(text, v)}
    return known


def _mentions(text: str, fact: str) -> bool:
    """True if `text` carries the fact: shares at least half of its distinctive words (numbers,
    ids, long words; every word if the fact has none). A heuristic: check it against labels."""
    words = [w.lower().strip(".,()'?:") for w in fact.split()]
    key = {w for w in words if any(c.isdigit() for c in w) or len(w) > 6} or set(words)
    have = {w.lower().strip(".,()'?:") for w in text.split()}
    return len(key & have) >= max(1, (len(key) + 1) // 2)


def turn_checks(sc: Scenario, s: Session) -> list[dict[str, Any]]:
    """One row per agent turn: what it asked, and whether that question was needed."""
    rows = []
    for i, text in enumerate(s.agent_turns):
        known = known_before(sc, s, i)
        asked = asked_facts(text) & set(sc.facts) if is_question(text) else set()
        rows.append(
            {
                "turn": i + 1,
                "kind": "question" if is_question(text) else "final" if is_final(text) else "other",
                "asked": sorted(asked),
                # Context retention: asking again for a fact the user already gave.
                "re_ask": bool(asked & known),
                # Clarification: a question although the opening already had everything needed.
                "needless": is_question(text) and not sc.missing,
                "one_question": text.count("?") <= 1,
            }
        )
    return rows


def resolved(sc: Scenario, s: Session) -> bool:
    """Session-level outcome: a final answer that names the scenario's cause."""
    return bool(s.final) and bool(re.search(sc.cause_terms, s.final.split("Next step:")[0], re.I))


def asked_when_needed(sc: Scenario, s: Session) -> bool | None:
    """Clarification behaviour when the opening lacked a needed fact (None if nothing was missing)."""
    if not sc.missing:
        return None
    return bool(s.agent_turns) and is_question(s.agent_turns[0])


def simulator_problems(sc: Scenario, s: Session) -> list[str]:
    """Check the simulated user, not the agent: did it volunteer facts nobody asked for, or say
    something that contradicts what it knows?"""
    problems = []
    for i, (role, text) in enumerate(s.turns):
        if role != "user" or i == 0:
            continue
        question = s.turns[i - 1][1]
        asked = asked_facts(question)
        for k, v in sc.facts.items():
            if _mentions(text, v) and k not in asked:
                problems.append(f"turn {i + 1}: volunteered '{k}' without being asked")
        if not any(_mentions(text, sc.facts[k]) for k in asked & set(sc.facts)) and asked & set(
            sc.facts
        ):
            problems.append(
                f"turn {i + 1}: did not give the asked fact ({', '.join(sorted(asked & set(sc.facts)))})"
            )
    return problems
