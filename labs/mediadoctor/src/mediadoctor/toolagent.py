"""MediaDoctor as a tool-using Claude agent, with every step traced (module 2).

The loop is the standard Messages API tool-use loop:

    1. send system prompt + tools + messages
    2. if stop_reason == "tool_use": run each requested tool, append the tool_result blocks, go to 1
    3. otherwise the text in the response is the answer

Span tree for one run (names follow the OpenTelemetry GenAI conventions):

    invoke_agent MediaDoctor
    ├─ chat claude-sonnet-5-5          one per model call: tokens, cost, latency, finish reason
    ├─ execute_tool ffprobe            one per tool call: arguments, result, error status
    ├─ execute_tool search_kb
    │  └─ retrieval                    query, top_k, returned doc ids and scores
    └─ chat claude-sonnet-5-5
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from evalkit import LLM, Tracer, load_models, load_prices, text_of
from evalkit.llm import incomplete_stop
from mediadoctor.tools import SIMULATED_TOOL_MS, TOOLS, ToolError, run_tool

AGENT_TOOLS_NAMESPACE = "mediadoctor-agent"
AGENT_NAME = "MediaDoctor"
MAX_RESULT_ATTR_CHARS = 2000

SYSTEM_AGENT_V1 = """\
You are MediaDoctor, an assistant for Android and multimedia engineers.

You have tools. When a question mentions a media file, a device, or a log file, use the tools to
gather evidence before answering. Use search_kb for background knowledge. Do not claim a tool
showed something unless the tool actually returned it.

Reply in exactly this format:
Likely cause: <one or two sentences, grounded in the evidence>
Next step: <the single most useful thing to check or change>
Sources: <[tool:<name>] for each tool whose output you relied on, and [kb:<id>] for documents>"""

# v2 (module 6) targets the false-premise failures found in modules 3 to 5: check what the user
# asserts before building on it. Module 6 measures whether it helped, per failure mode.
SYSTEM_AGENT_V2 = """\
You are MediaDoctor, an assistant for Android and multimedia engineers.

You have tools. When a question mentions a media file, a device, or a log file, use the tools to
gather evidence before answering. Use search_kb for background knowledge. Do not claim a tool
showed something unless the tool actually returned it.

Users sometimes state things that are not true: an API level, what a device supports, or what
caused a problem. Check every such claim against the tool output or the knowledge base before you
rely on it, and say plainly when it does not hold.

Reply in exactly this format:
Likely cause: <one or two sentences, grounded in the evidence>
Next step: <the single most useful thing to check or change>
Sources: <[tool:<name>] for each tool whose output you relied on, and [kb:<id>] for documents>"""

AGENT_PROMPTS = {"v1": SYSTEM_AGENT_V1, "v2": SYSTEM_AGENT_V2}


@dataclass
class AgentResult:
    answer: str
    trace_id: str
    stop_reason: str
    steps: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def _truncate(s: str, n: int = MAX_RESULT_ATTR_CHARS) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def build_request(messages: list[dict[str, Any]], prompt_version: str = "v1") -> dict[str, Any]:
    role = load_models()["agent"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": AGENT_PROMPTS[prompt_version],
        "tools": TOOLS,
        # Deep copy: the request is hashed and may be stored, and we keep appending to messages.
        "messages": copy.deepcopy(messages),
    }


def run_agent(
    question: str,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
    case_id: str | None = None,
    prompt_version: str = "v1",
    max_steps: int = 6,
) -> AgentResult:
    llm = llm or LLM(namespace=AGENT_TOOLS_NAMESPACE)
    tracer = tracer or Tracer()
    role = load_models()["agent"]
    price = load_prices().get(role.model)
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    totals = {"in": 0, "out": 0, "cost": 0.0}
    answer, stop, steps = "", "max_steps", 0

    root_attrs = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": AGENT_NAME,
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": role.model,
        "gen_ai.prompt.name": "mediadoctor-agent",
        "gen_ai.prompt.version": prompt_version,
        "mediadoctor.case.id": case_id,
        "mediadoctor.question": question,
    }
    with tracer.span(f"invoke_agent {AGENT_NAME}", root_attrs) as root:
        for step in range(1, max_steps + 1):
            steps = step
            request = build_request(messages, prompt_version)
            with tracer.span(
                f"chat {role.model}",
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "anthropic",
                    "gen_ai.request.model": role.model,
                    "gen_ai.request.max_tokens": role.max_tokens,
                    "mediadoctor.step": step,
                },
                kind="CLIENT",
            ) as sp:
                resp = llm.create(**request)
                tracer.clock.advance(llm.last_latency_ms or 0.0)  # moves only the virtual clock
                usage = resp.get("usage", {})
                tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
                cost = price.cost_usd(tin, tout) if price else 0.0
                sp.set_attributes(
                    {
                        "gen_ai.response.id": resp.get("id"),
                        "gen_ai.response.model": resp.get("model"),
                        "gen_ai.response.finish_reasons": [str(resp.get("stop_reason"))],
                        "gen_ai.usage.input_tokens": tin,
                        "gen_ai.usage.output_tokens": tout,
                        "gen_ai.usage.cache_read.input_tokens": usage.get(
                            "cache_read_input_tokens"
                        ),
                        "gen_ai.usage.cache_write.input_tokens": usage.get(
                            "cache_creation_input_tokens"
                        ),
                        "evalkit.cost.usd": round(cost, 6),
                        "evalkit.replayed": llm.last_replayed,
                    }
                )
                totals["in"] += tin
                totals["out"] += tout
                totals["cost"] += cost

            messages.append({"role": "assistant", "content": resp["content"]})
            if resp.get("stop_reason") != "tool_use":
                answer, stop = text_of(resp), str(resp.get("stop_reason"))
                break

            results = []
            for block in resp["content"]:
                if block.get("type") != "tool_use":
                    continue
                name, args = block["name"], block.get("input", {})
                with tracer.span(
                    f"execute_tool {name}",
                    {
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.tool.name": name,
                        "gen_ai.tool.type": "function",
                        "gen_ai.tool.call.id": block["id"],
                        "gen_ai.tool.call.arguments": json.dumps(args, sort_keys=True),
                    },
                ) as ts:
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
            messages.append({"role": "user", "content": results})

        root.set_attributes(
            {
                "mediadoctor.stop_reason": stop,
                "mediadoctor.steps": steps,
                "mediadoctor.answer": answer,
                "gen_ai.usage.input_tokens": totals["in"],
                "gen_ai.usage.output_tokens": totals["out"],
                "evalkit.cost.usd": round(totals["cost"], 6),
            }
        )
        if stop == "max_steps":
            root.set_error(f"stopped after {max_steps} steps without a final answer", "MaxSteps")
        elif why := incomplete_stop(stop):
            root.set_error(why, "IncompleteStop")
        trace_id = root.trace_id

    return AgentResult(answer, trace_id, stop, steps, totals["in"], totals["out"], totals["cost"])
