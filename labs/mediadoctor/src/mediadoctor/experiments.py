"""Module 11: MediaDoctor configurations for accuracy, latency, and cost experiments.

A *variant* (config/experiments/variants.toml) fixes a prompt version, a model, whether the tools and
system prompt are cached, and a strategy:

    single    one agent run
    cascade   the cheap model runs first; if its answer fails a code check (format, citations,
              investigated), the expensive model runs the task again from scratch
    retry     after the agent answers, a cheap judge reviews the answer; on FAIL the agent gets the
              critique and one more chance in the same conversation

Every task is graded the same way, whatever the variant: module 5's code checks plus a reference
check of the diagnosis (`check_correct`), and its cost (from the usage of every call, cache tokens
included, priced from config/models.toml) and latency (the trace's wall time) are summed over all
attempts and self-checks.
"""

from __future__ import annotations

import copy
import json
import re
import tomllib
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from evalkit import LLM, Tracer, load_prices, repo_root, text_of
from mediadoctor import lab04, lab05
from mediadoctor.toolagent import AGENT_NAME, SYSTEM_AGENT_V1, SYSTEM_AGENT_V2
from mediadoctor.tools import SIMULATED_TOOL_MS, TOOLS, ToolError, run_tool

MAX_TOKENS = 1024
SELF_CHECK_MAX_TOKENS = 300
MAX_RESULT_ATTR_CHARS = 2000
JUDGE_NAMESPACE = "mediadoctor-m11-selfcheck"

# v3 targets the two modes with the highest expected value of fixing in module 3's taxonomy
# (`uv run mediadoctor-lab11 ev`): answers that contradict the tool output, and citations of tools that
# never ran. The two examples were chosen from module 3's traces with those failures (m3t059 and
# m3t065) and rewritten as correct answers; they are not in the module 4 dataset the lab evaluates on.
FEW_SHOT_SOURCES = ("m3t059", "m3t065")
SYSTEM_AGENT_V3 = """\
You are MediaDoctor, an assistant for Android and multimedia engineers.

You have tools. When a question mentions a media file, a device, or a log file, use the tools to
gather evidence before answering. Use search_kb for background knowledge. Do not claim a tool
showed something unless the tool actually returned it.

Users sometimes state things that are not true: an API level, what a device supports, or what
caused a problem. Check every such claim against the tool output or the knowledge base before you
rely on it, and say plainly when it does not hold.

Ground the cause in the evidence: quote the exact value from the tool output that your cause
depends on (a start_time, a box order, a decoder name and its hardware flag, a log line). If the
tool output contradicts what you expected, the tool output wins. Cite only tools that returned a
result; if a call failed, say so and do not cite it.

Reply in exactly this format:
Likely cause: <one or two sentences, grounded in the evidence>
Next step: <the single most useful thing to check or change>
Sources: <[tool:<name>] for each tool whose output you relied on, and [kb:<id>] for documents>

Example 1
Question: Voices lead lip movement on one encoder output (av_offset_300ms.mp4). Player bug or file?
(ffprobe returned: audio start_time 0.000000, video start_time 0.300000)
Likely cause: The file itself is offset: ffprobe shows the video stream's start_time is 0.300000
while audio starts at 0.000000, so a player that honours start times shows audio 300 ms early.
Next step: Remux with the video start time corrected (for example ffmpeg -itsoffset) and re-test.
Sources: [tool:ffprobe] [kb:av-sync]

Example 2
Question: lumen-l3: thumbnails go blank and we get codec errors (thumbs_codec_exhaustion.txt).
(logcat_grep on thumbs.txt failed: file not found; on thumbs_codec_exhaustion.txt it returned
"E CCodec: Failed to create component ... (NO_MEMORY: max instances reached)")
Likely cause: The grid creates more video decoders than the device allows: the log shows
"NO_MEMORY: max instances reached" when the next decoder is created; this is a codec instance limit,
not Java heap memory.
Next step: Reuse a small pool of decoders (or extract thumbnails one at a time) and release each
codec when its cell scrolls away.
Sources: [tool:logcat_grep] [kb:mediacodec-errors]"""

PROMPTS = {"v1": SYSTEM_AGENT_V1, "v2": SYSTEM_AGENT_V2, "v3": SYSTEM_AGENT_V3}

SELF_CHECK_SYSTEM = """\
You review answers written by MediaDoctor, an assistant for Android media engineers, before the
user sees them. You get the user's question, the evidence the tools returned, and the answer.

FAIL the answer if any of these is true:
- the Likely cause is not supported by the evidence, or contradicts it;
- the user asserted something and the answer builds on it without checking it;
- the answer cites a tool or document that does not appear in the evidence;
- the question names a file, device, or log and no tool inspected it;
- the answer is not in the three-line format (Likely cause, Next step, Sources).
Otherwise PASS.

Reply in exactly this format:
CRITIQUE: <one sentence naming the main problem, or "none">
VERDICT: PASS or FAIL"""

RETRY_TEMPLATE = (
    "A reviewer checked your answer and found a problem: {critique}\n"
    "Investigate again if you need to, then reply in the same format."
)


# --- Variants -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    parent: str
    change: str
    prompt: str
    model: str
    cache: bool
    strategy: str = "single"
    escalate_to: str = ""
    judge: str = ""


def variants_path():
    return repo_root() / "config" / "experiments" / "variants.toml"


@cache
def variants() -> dict[str, Variant]:
    raw = tomllib.loads(variants_path().read_text(encoding="utf-8"))["variants"]
    out = {}
    for name, v in raw.items():
        var = Variant(name=name, **v)
        if var.prompt not in PROMPTS or var.strategy not in ("single", "cascade", "retry"):
            raise ValueError(f"variant {name}: unknown prompt or strategy")
        out[name] = var
    return out


def short_model(model: str) -> str:
    for family in ("sonnet", "haiku", "opus"):
        if family in model:
            return family
    return model


def namespace(model: str, prompt: str, cached: bool) -> str:
    """Fixture namespace for one (model, prompt, caching) combination. Variants that send the same
    requests share it: the cascade's first attempt is the Haiku variant's run, its escalations are
    the v3-cache runs, and the retry variant's first attempt is a v3-cache run too."""
    return f"mediadoctor-m11-{short_model(model)}-{prompt}{'-cache' if cached else ''}"


@cache
def llm_for(ns: str) -> LLM:
    return LLM(namespace=ns)


# --- Requests -------------------------------------------------------------------------------------------


def system_param(prompt: str, cached: bool) -> str | list[dict[str, Any]]:
    """The system prompt; with caching, one text block with a cache breakpoint at its end, which
    caches the whole prefix before it (tools, then system)."""
    text = PROMPTS[prompt]
    if not cached:
        return text
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def build_request(
    model: str, prompt: str, cached: bool, messages: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_param(prompt, cached),
        "tools": TOOLS,
        "messages": copy.deepcopy(messages),
    }


def self_check_request(model: str, question: str, evidence: str, answer: str) -> dict[str, Any]:
    content = (
        f"<question>\n{question}\n</question>\n<evidence>\n{evidence or '(no tool output)'}\n"
        f"</evidence>\n<answer>\n{answer}\n</answer>"
    )
    return {
        "model": model,
        "max_tokens": SELF_CHECK_MAX_TOKENS,
        "system": SELF_CHECK_SYSTEM,
        "messages": [{"role": "user", "content": content}],
    }


def parse_self_check(text: str) -> tuple[bool, str]:
    m = re.search(r"VERDICT:\s*(PASS|FAIL)", text)
    if not m:
        raise ValueError(f"unparseable self-check output: {text[:80]!r}")
    c = re.search(r"CRITIQUE:\s*(.+)", text)
    return m.group(1) == "PASS", (c.group(1).strip() if c else "")


# --- Usage and cost ------------------------------------------------------------------------------------


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0  # uncached input
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: Usage) -> None:
        for f in (
            "calls",
            "input_tokens",
            "output_tokens",
            "cache_write_tokens",
            "cache_read_tokens",
        ):
            setattr(self, f, getattr(self, f) + getattr(other, f))
        self.cost_usd += other.cost_usd


def call_usage(model: str, usage: dict[str, Any]) -> Usage:
    tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    cw = int(usage.get("cache_creation_input_tokens") or 0)
    cr = int(usage.get("cache_read_input_tokens") or 0)
    price = load_prices().get(model)
    cost = price.cost_usd(tin, tout, cw, cr) if price else 0.0
    return Usage(1, tin, tout, cw, cr, cost)


# --- Runs ----------------------------------------------------------------------------------------------


@dataclass
class Attempt:
    model: str
    answer: str
    spans: list[dict[str, Any]]
    usage: Usage
    latency_ms: float
    self_check: bool | None = None  # the judge's verdict (retry strategy), None if not checked
    retried: bool = False


def _truncate(s: str, n: int = MAX_RESULT_ATTR_CHARS) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _chat(tracer: Tracer, llm: LLM, request: dict[str, Any], step: int, usage: Usage, **attrs):
    model = request["model"]
    with tracer.span(
        f"chat {model}",
        {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",
         "gen_ai.request.model": model, "gen_ai.request.max_tokens": request["max_tokens"],
         "mediadoctor.step": step, **attrs},
        kind="CLIENT",
    ) as sp:  # fmt: skip
        resp = llm.create(**request)
        tracer.clock.advance(llm.last_latency_ms or 0.0)
        u = call_usage(model, resp.get("usage", {}))
        sp.set_attributes(
            {
                "gen_ai.response.id": resp.get("id"),
                "gen_ai.response.model": resp.get("model"),
                "gen_ai.response.finish_reasons": [str(resp.get("stop_reason"))],
                "gen_ai.usage.input_tokens": u.input_tokens,
                "gen_ai.usage.output_tokens": u.output_tokens,
                "gen_ai.usage.cache_read.input_tokens": u.cache_read_tokens,
                "gen_ai.usage.cache_write.input_tokens": u.cache_write_tokens,
                "evalkit.cost.usd": round(u.cost_usd, 8),
                "evalkit.replayed": llm.last_replayed,
            }
        )
        usage.add(u)
    return resp


def _tools(tracer: Tracer, resp: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for block in resp["content"]:
        if block.get("type") != "tool_use":
            continue
        name, args = block["name"], block.get("input", {})
        with tracer.span(
            f"execute_tool {name}",
            {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name,
             "gen_ai.tool.type": "function", "gen_ai.tool.call.id": block["id"],
             "gen_ai.tool.call.arguments": json.dumps(args, sort_keys=True)},
        ) as ts:  # fmt: skip
            is_error = False
            try:
                output = run_tool(name, args, tracer=tracer)
            except ToolError as exc:
                output, is_error = f"Error: {exc}", True
                ts.set_error(str(exc), "ToolError")
            tracer.clock.advance(SIMULATED_TOOL_MS.get(name, 1.0))
            ts.set_attribute("gen_ai.tool.call.result", _truncate(output))
        result = {"type": "tool_result", "tool_use_id": block["id"], "content": output}
        if is_error:
            result["is_error"] = True
        results.append(result)
    return results


def evidence_of(spans: list[dict[str, Any]], n: int = 700) -> str:
    """What the tools returned, as the self-check judge sees it."""
    lines = []
    for s in spans:
        a = s["attributes"]
        if a.get("gen_ai.operation.name") == "execute_tool":
            ok = s["status"]["code"] != "ERROR"
            res = str(a.get("gen_ai.tool.call.result", ""))
            lines.append(f"[{a['gen_ai.tool.name']}{'' if ok else ' FAILED'}] {res[:n]}")
    return "\n".join(lines)


def run_attempt(
    case: dict[str, Any], variant: Variant, model: str, attempt: int = 1,
    llm: LLM | None = None, judge_llm: LLM | None = None, max_steps: int = 6,
) -> Attempt:  # fmt: skip
    """One agent run of `model` on the case. With variant.strategy == "retry", the answer is
    self-checked by variant.judge and, on FAIL, the conversation continues once with the critique."""
    llm = llm or llm_for(namespace(model, variant.prompt, variant.cache))
    tracer = Tracer.for_replay(f"m11:{variant.name}:{case['id']}:{attempt}")
    usage = Usage()
    messages: list[dict[str, Any]] = [{"role": "user", "content": case["question"]}]
    answer, stop, step, verdict, retried, critique = "", "max_steps", 0, None, False, ""
    root_attrs = {
        "gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": AGENT_NAME,
        "gen_ai.provider.name": "anthropic", "gen_ai.request.model": model,
        "gen_ai.prompt.name": "mediadoctor-agent", "gen_ai.prompt.version": variant.prompt,
        "mediadoctor.case.id": case["id"], "mediadoctor.question": case["question"],
        "mediadoctor.variant": variant.name, "mediadoctor.attempt": attempt,
        "mediadoctor.cache": variant.cache,
    }  # fmt: skip
    with tracer.span(f"invoke_agent {AGENT_NAME}", root_attrs) as root:
        budget = max_steps
        while step < budget:
            step += 1
            resp = _chat(
                tracer,
                llm,
                build_request(model, variant.prompt, variant.cache, messages),
                step,
                usage,
            )  # noqa: E501
            messages.append({"role": "assistant", "content": resp["content"]})
            if resp.get("stop_reason") == "tool_use":
                messages.append({"role": "user", "content": _tools(tracer, resp)})
                continue
            answer, stop = text_of(resp), str(resp.get("stop_reason"))
            if variant.strategy != "retry" or verdict is not None:
                break
            req = self_check_request(
                variant.judge, case["question"], evidence_of(tracer.span_dicts()), answer
            )  # noqa: E501
            jr = _chat(tracer, judge_llm or llm_for(JUDGE_NAMESPACE), req, step, usage,
                       **{"mediadoctor.self_check": True})  # fmt: skip
            verdict, critique = parse_self_check(text_of(jr))
            if verdict:
                break
            retried = True
            messages.append({"role": "user", "content": RETRY_TEMPLATE.format(critique=critique)})
            budget = step + max_steps // 2
        root.set_attributes(
            {
                "mediadoctor.stop_reason": stop,
                "mediadoctor.steps": step,
                "mediadoctor.answer": answer,
                "mediadoctor.self_check": verdict,
                "mediadoctor.retried": retried,
                "mediadoctor.critique": critique or None,
                "gen_ai.usage.input_tokens": usage.input_tokens,
                "gen_ai.usage.output_tokens": usage.output_tokens,
                "evalkit.cost.usd": round(usage.cost_usd, 8),
            }
        )
    spans = tracer.span_dicts()
    r = next(s for s in spans if s["parent_span_id"] is None)
    latency = (r["end_time_unix_nano"] - r["start_time_unix_nano"]) / 1e6
    return Attempt(model, answer, spans, usage, latency, verdict, retried)


# --- Grading --------------------------------------------------------------------------------------------

# The reference diagnosis for each module 3 scenario (mediadoctor.lab04.scenario_for): the fact the
# Likely cause must state, and, where module 4's false premises corrupt the next step instead, the
# wrong API claim the Next step must not make. A reference check standing in for module 5's
# validated judges, so the lab can grade thousands of answers offline; tests check it against the
# known right and wrong answers for every scenario.
REFERENCE: dict[str, tuple[str, str | None]] = {
    "av1-lumen": (r"only has the software decoder", None),
    "av1-atlas": (r"hardware AV1 decoder for Main", None),
    "hdr-lumen": (r"supports Main, not Main 10", None),
    "hdr-atlas": (r"Main10HDR10", None),
    "latemoov": (r"ftyp, free, mdat, moov", None),
    "faststart": (r"ftyp, moov, free, mdat", None),
    "avoffset": (r"video stream starts at 0\.300", None),
    "thumbs": (r"max instances reached", None),
    "live": (r"BehindLiveWindowException", None),
    "audiofocus": (r"audio focus", r"from API 21"),
    "widevine": (r"security level L3", None),
    "main10": (r"supports the Main profile, not Main 10", None),
    "av1-api": (r"API 29", r"API 26\) added"),
    "hdr-display-api": (r"Display object", r"available from API 21"),
}
CHECKS = ("format", "citations", "investigated", "correct")


def answer_line(answer: str, label: str) -> str:
    m = re.search(rf"^{label}:(.*)$", answer, re.M)
    return m.group(1) if m else ""


def check_correct(answer: str, case: dict[str, Any]) -> bool:
    """The right diagnosis: the Likely cause states the scenario's key fact and the Next step does not
    repeat a known-wrong API claim."""
    cause_re, wrong_next = REFERENCE[lab04.scenario_for(case)]
    if not re.search(cause_re, answer_line(answer, "Likely cause")):
        return False
    return not (wrong_next and re.search(wrong_next, answer_line(answer, "Next step")))


def cases() -> list[dict[str, Any]]:
    """Module 4's dataset rows that exercise a module 3 scenario (module 5's 137 agent queries)."""
    return lab05.label_rows()


def grade(spans: list[dict[str, Any]], case: dict[str, Any]) -> dict[str, bool]:
    out = {name: bool(fn(spans, case)) for name, (_mode, fn) in lab05.CODE_CHECKS.items()}
    out["correct"] = check_correct(lab05.item_from_trace(spans).answer, case)
    return out


def code_checks_pass(spans: list[dict[str, Any]], case: dict[str, Any]) -> bool:
    """What the cascade can check without a reference: format, citations, investigated."""
    return all(fn(spans, case) for _mode, fn in lab05.CODE_CHECKS.values())


# --- Tasks ----------------------------------------------------------------------------------------------


@dataclass
class TaskResult:
    case_id: str
    variant: str
    checks: dict[str, bool]
    answer: str
    usage: Usage
    latency_ms: float
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def graded_success(self) -> bool:
        return all(self.checks.values())

    @property
    def escalated(self) -> bool:
        return len(self.attempts) > 1

    @property
    def retried(self) -> bool:
        return any(a.retried for a in self.attempts)

    @property
    def models(self) -> list[str]:
        return [a.model for a in self.attempts]


def run_task(case: dict[str, Any], variant: Variant | str) -> TaskResult:
    v = variants()[variant] if isinstance(variant, str) else variant
    attempts = [run_attempt(case, v, v.model, 1)]
    if v.strategy == "cascade" and not code_checks_pass(attempts[0].spans, case):
        attempts.append(run_attempt(case, v, v.escalate_to, 2))
    final = attempts[-1]
    usage = Usage()
    for a in attempts:
        usage.add(a.usage)
    return TaskResult(
        case["id"], v.name, grade(final.spans, case), final.answer, usage,
        sum(a.latency_ms for a in attempts), attempts,
    )  # fmt: skip
