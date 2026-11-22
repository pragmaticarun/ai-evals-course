# Cheat sheet: tracing an agent

## What to put in a trace

```text
invoke_agent mediadoctor            one run: case id, prompt version, answer, steps, total cost
├─ chat {model}                     every model call: tokens in/out, stop reason, latency, cost
├─ execute_tool {name}              every tool call: arguments, result (or error), latency
│  └─ retrieval                     every search: query, returned doc ids and scores
└─ chat {model}                     ...
```

## Attribute names

| Need | Use | Standard? |
|---|---|---|
| Operation kind | `gen_ai.operation.name` (`invoke_agent`, `chat`, `execute_tool`, `retrieval`) | OTel GenAI |
| Model | `gen_ai.request.model`, `gen_ai.response.model` | OTel GenAI |
| Tokens | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | OTel GenAI |
| Why the model stopped | `gen_ai.response.finish_reasons` | OTel GenAI |
| Tool | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` | OTel GenAI (opt-in content) |
| Failure | span status `ERROR` + `error.type` | OTel core |
| Your domain | `yourapp.*` (here `mediadoctor.*`, `evalkit.*`) | Yours: never invent `gen_ai.*` names |

The GenAI conventions are still marked *development*; check [the current spec](https://github.com/open-telemetry/semantic-conventions-genai) before pinning names.

## Commands

```bash
uv run mediadoctor-lab02 run --out runs/t.jsonl          # run all cases, write spans
uv run mediadoctor-lab02 run --case m2q03                # one case
uv run evalkit view runs/t.jsonl                         # one line per trace
uv run evalkit view runs/t.jsonl m2q03 --results         # tree with tool results
uv run evalkit view runs/t.jsonl m2q04 --all             # every attribute
uv run evalkit otlp runs/t.jsonl -o runs/otlp.json --openinference
```

## Trace checks worth writing early

| Check | Catches |
|---|---|
| Evidence is real: every cited tool has a successful span | Fabricated citations |
| Expected tools succeeded | Skipped investigation |
| No repeated retrieval (same docs twice) | Loops, wasted tokens |
| Step budget (model calls ≤ N) | Runaway cost and latency |
| Root span status OK | Max-steps stops, crashes |

## Reading order for a bad trace

1. Root: final answer, steps, cost. Is it bad, slow, or expensive?
2. First tool span with an error, or the first surprising result.
3. The model call right after it: did the model notice?
4. Stop there and name the first upstream failure (module 3 counts them).

## Making traces reproducible

- Replay model calls from fixtures; make tools deterministic (cache external tool output).
- Use a virtual clock and seeded ids in replay; wall clock and random ids live.
- Keep your own JSONL export even if you also use a backend: it is what CI replays.

## Red flags

- Tool errors that never reach the trace (swallowed exceptions).
- Traces without token counts: you cannot explain cost.
- Secrets or user data in tool arguments with no redaction policy.
- A dashboard nobody has used to open a single trace.
