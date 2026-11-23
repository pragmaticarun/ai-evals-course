"""MediaDoctor split into a planner and specialists (module 7).

    planner ──route + brief──> media specialist   (ffprobe, search_kb)
            └─────────────────> device specialist  (codec_caps, logcat_grep, search_kb)
            └─────────────────> knowledge specialist (search_kb)
    planner <──findings─────── each specialist, in route order
    planner ──final answer──> user

A specialist sees only the planner's brief (and earlier specialists' findings), never the user's
message. That boundary is where handoff errors happen: a brief that drops the file name leaves the
specialist guessing. Every step is recorded in a `Step` list (the trajectory) for evaluation.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

from evalkit import LLM, load_models, text_of
from evalkit.llm import incomplete_stop
from mediadoctor.tools import TOOLS, ToolError, run_tool

NAMESPACE = "mediadoctor-m7-agents"
MAX_SPECIALIST_CALLS = 3

SPECIALISTS: dict[str, tuple[str, ...]] = {
    "media": ("ffprobe", "search_kb"),
    "device": ("codec_caps", "logcat_grep", "search_kb"),
    "knowledge": ("search_kb",),
}

PLANNER_SYSTEM = """\
You are the planner of MediaDoctor, an assistant for Android and multimedia engineers. You do not
investigate yourself; you route each question to specialists:

- media: inspects media files with ffprobe, and searches the knowledge base
- device: checks a device's decoders and capabilities (codec_caps) and captured logs (logcat_grep),
  and searches the knowledge base
- knowledge: answers general questions from the knowledge base only

Pick one or two specialists, in the order they should work. Write one brief for them. They see only
your brief, never the user's message, so the brief must include every file name, device, log file,
and timestamp the user mentioned, and the symptom.

Reply with JSON only: {"route": ["<specialist>", ...], "brief": "<brief>"}"""

SPECIALIST_SYSTEM = """\
You are the {name} specialist in MediaDoctor's team. You receive a brief from the planner.
Investigate it with your tools, then reply with one line that starts with "Findings:" and states
what the evidence shows. Quote tool output; do not guess beyond it."""

WRITER_SYSTEM = """\
You are the planner of MediaDoctor. Write the final answer to the user's question from your
specialists' findings. Do not claim anything the findings do not show.

Reply in exactly this format:
Likely cause: <one or two sentences, grounded in the findings>
Next step: <the single most useful thing to check or change>
Sources: <[tool:<name>] for each tool whose output the findings relied on>"""

_JSON = re.compile(r"\{.*\}", re.S)


@dataclass(frozen=True)
class Step:
    kind: str  # plan | handoff | tool | findings | answer
    agent: str  # planner or the specialist's name
    name: str = ""  # tool name for tool steps
    args: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    text: str = ""  # brief, tool result, findings, or answer


@dataclass
class Run:
    case_id: str
    question: str
    route: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    model_calls: int = 0

    @property
    def answer(self) -> str:
        return next((s.text for s in reversed(self.steps) if s.kind == "answer"), "")

    @property
    def tool_steps(self) -> list[Step]:
        return [s for s in self.steps if s.kind == "tool"]


def _request(system: str, messages: list[dict[str, Any]], tools: tuple[str, ...] = ()) -> dict:
    role = load_models()["agent"]
    req: dict[str, Any] = {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": system,
        "messages": copy.deepcopy(messages),
    }
    if tools:
        req["tools"] = [t for t in TOOLS if t["name"] in tools]
    return req


def parse_plan(text: str) -> tuple[list[str], str]:
    m = _JSON.search(text)
    try:
        obj = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        obj = {}
    route = [r for r in obj.get("route", []) if r in SPECIALISTS] if isinstance(obj, dict) else []
    return route, str(obj.get("brief", "")) if isinstance(obj, dict) else ""


def run_specialist(name: str, brief: str, earlier: list[str], llm: LLM, run: Run) -> str:
    content = f"Brief from the planner: {brief}"
    if earlier:
        content += "\n\nFindings so far:\n" + "\n".join(earlier)
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    system = SPECIALIST_SYSTEM.format(name=name)
    for _ in range(MAX_SPECIALIST_CALLS):
        resp = llm.create(**_request(system, messages, SPECIALISTS[name]))
        run.model_calls += 1
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp.get("stop_reason") != "tool_use":
            findings = text_of(resp).strip()
            # A truncated or declined reply is not findings the planner can rely on.
            ok = incomplete_stop(resp.get("stop_reason")) is None
            run.steps.append(Step("findings", name, ok=ok, text=findings))
            return findings
        results = []
        for block in resp["content"]:
            if block.get("type") != "tool_use":
                continue
            tool, args = block["name"], block.get("input", {})
            try:
                if tool not in SPECIALISTS[name]:
                    raise ToolError(f"tool {tool!r} is not available to the {name} specialist")
                out, ok = run_tool(tool, args), True
            except ToolError as exc:
                out, ok = f"Error: {exc}", False
            run.steps.append(Step("tool", name, tool, dict(args), ok, out))
            result = {"type": "tool_result", "tool_use_id": block["id"], "content": out}
            if not ok:
                result["is_error"] = True
            results.append(result)
        messages.append({"role": "user", "content": results})
    run.steps.append(Step("findings", name, ok=False, text="(no findings: step limit)"))
    return ""


def run_team(question: str, case_id: str, llm: LLM | None = None) -> Run:
    llm = llm or LLM(namespace=NAMESPACE)
    run = Run(case_id, question)
    plan = text_of(llm.create(**_request(PLANNER_SYSTEM, [{"role": "user", "content": question}])))
    run.model_calls += 1
    route, brief = parse_plan(plan)
    run.route = route
    run.steps.append(Step("plan", "planner", args={"route": route}, ok=bool(route), text=plan))
    findings: list[str] = []
    for name in route:
        run.steps.append(Step("handoff", "planner", name, {"to": name}, True, brief))
        f = run_specialist(name, brief, findings, llm, run)
        findings.append(f"- {name}: {f}")
    writer_input = f"Question: {question}\n\nFindings:\n" + ("\n".join(findings) or "(none)")
    answer = text_of(
        llm.create(**_request(WRITER_SYSTEM, [{"role": "user", "content": writer_input}]))
    )
    run.model_calls += 1
    run.steps.append(Step("answer", "planner", text=answer.strip()))
    return run
