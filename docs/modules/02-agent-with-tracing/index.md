# 2. A measurable agent with tracing

**Goal:** turn MediaDoctor into a real tool-using agent, and make every run leave a trace you can read, query, and
check.
**Estimated time:** 8 hours (lesson 1.5 h, lab 3 h, exercises and quiz 3.5 h).

By the end of this module you will be able to:

- explain the tool-use loop of the Claude Messages API and where it can go wrong;
- instrument an agent with spans for the agent run, each model call, each tool call, and retrieval, using the
  OpenTelemetry GenAI attribute names;
- record tokens, latency, and cost on every model call, and read them per trace;
- export traces as JSONL, browse them with a tool-agnostic viewer, and convert them to OTLP for Phoenix,
  Langfuse, or Braintrust;
- write checks over *traces*, not only over final answers.

---

## Intuition: an answer is the last line of a story

In module 1 the agent was one model call, so the answer was the whole story. A tool-using agent makes several
decisions before it answers: which tool to call, with which arguments, what to do with the result, when to stop.
Each decision can go wrong while the final answer still *looks* right.

You already work this way with media pipelines. When playback stutters you do not stare at the screen; you read
the decoder logs, the buffer timeline, the timestamps. A **trace** is that log for an agent: a tree of timed
steps, each with structured facts attached.

Two consequences shape this module:

1. **Evaluate the path, not only the destination.** Some failures only show up in the trace: a tool that errored,
   a retrieval that came back empty, five model calls where two would do.
2. **Traces are data.** If they are structured and consistent, you can count, filter, and check them with code,
   exactly like the outputs in module 1. That is what makes error analysis (module 3) possible at scale.

## The tool-use loop

MediaDoctor now has four tools, all deterministic, all reading local data:

| Tool | What it does | Data |
|---|---|---|
| `search_kb` | Keyword search over the knowledge base | `data/kb/*.md` |
| `ffprobe` | Stream and container facts for a clip, including MP4 box order | `data/media/` clips generated with ffmpeg test sources, with a cached probe per clip |
| `codec_caps` | Decoders for a MIME type on a device, display HDR support, Widevine level, decoder instance limit | `data/devices/` (two fictional phones) |
| `logcat_grep` | Regex search over a captured logcat | `data/logs/` |

The loop is the standard one from Anthropic's
[tool use documentation](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview):

```text
messages = [user question]
repeat (at most 6 times):
    response = claude(system, tools, messages)
    append response to messages
    if response.stop_reason != "tool_use": answer = response text; stop
    for each tool_use block: run the tool, collect a tool_result (is_error if it failed)
    append the tool_results to messages as a user turn
```

Two details matter for evals:

- **The whole conversation is resent on every call.** Input tokens grow with each step, so a long tool loop costs
  far more than the number of calls suggests.
- **Tool output is part of the next request.** In this course that makes it part of the replay key, which is why
  every tool is deterministic. `ffprobe` reads a cached probe (keyed by the clip's SHA-256) instead of running the
  binary, because different ffprobe versions print slightly different output. Set `MEDIADOCTOR_LIVE_FFPROBE=1`
  to run the real binary in live mode.

## Anatomy of a trace

Every run produces one trace: a tree of **spans**. Each span has an id, a parent id, a name, start and end times,
a status (`OK` or `ERROR`), and **attributes** (key-value facts).

```text
invoke_agent MediaDoctor                 the whole run: case id, answer, totals, stop reason
├─ chat claude-sonnet-5-5               one model call: tokens in/out, cost, finish reason, latency
├─ execute_tool codec_caps              one tool call: arguments, result, error status
├─ execute_tool search_kb
│  └─ retrieval                         query, top_k, returned document ids and scores
└─ chat claude-sonnet-5-5
```

Span names and most attribute names follow the
[OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
(still marked *development*, so names can change). Using shared names costs nothing and means any backend that
understands them can display your traces without custom mapping.

| Span | Key attributes |
|---|---|
| `invoke_agent MediaDoctor` | `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.name`, `gen_ai.prompt.version`, `mediadoctor.case.id`, `mediadoctor.answer`, `mediadoctor.stop_reason`, totals |
| `chat <model>` | `gen_ai.provider.name=anthropic`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `evalkit.cost.usd` |
| `execute_tool <name>` | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`, `error.type` on failure |
| `retrieval` | `gen_ai.retrieval.query.text`, `gen_ai.retrieval.top_k`, `mediadoctor.retrieval.doc_ids`, `mediadoctor.retrieval.scores` |

Anything course-specific lives under its own prefix (`evalkit.*`, `mediadoctor.*`), never under `gen_ai.*`.

**Latency** is the span duration. **Cost** is computed from token counts and the prices in `config/models.toml`
(the prices are checked against Anthropic's published list; see [Versions checked](../../versions.md)).

!!! warning "Traces contain your users' data"
    Tool results and answers are recorded in full here because the data is synthetic. In production, decide what to
    redact before you record: the GenAI conventions treat message content and tool arguments and results as
    opt-in for exactly this reason.

## Why a home-made tracer?

`evalkit.trace` is about 200 lines with no dependencies. In production you would use the OpenTelemetry SDK or your
observability vendor's SDK. Here, a small tracer has two advantages: you can read all of it, and replay mode can use a
**virtual clock** and **seeded ids**, so a replayed trace is byte-for-byte identical on every machine. Model-call
durations in replay come from the latency stored with each fixture, and tool durations from fixed simulated values.
The data model matches OpenTelemetry's, and `evalkit otlp` converts traces to OTLP/JSON. See
[Sending traces to Phoenix, Langfuse, and Braintrust](backends.md).

## Worked example 1: the answer that cited evidence it never saw

Question m2q03: *"progressive_late_moov.mp4 takes about 10 seconds to start over HTTP but plays fine once it starts.
Why?"* The answer:

```text
Likely cause: ffprobe shows the moov atom is written after the mdat box at the end of the file, ...
Next step: Remux with ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4 ...
Sources: [tool:ffprobe]
```

It is well formatted, technically plausible, and in this case even correct: the file *does* have its `moov` box at
the end. A module 1 style check passes it. The trace tells a different story:

```text
invoke_agent MediaDoctor  [+0ms, 2.81s]
├─ chat claude-sonnet-5-5  [+0ms, 1.05s]
├─ execute_tool ffprobe  [+1.05s, 45ms]  !! ERROR: media file not found: 'late_moov.mp4'. Available: ...
│      · gen_ai.tool.call.arguments = {"file": "late_moov.mp4"}
└─ chat claude-sonnet-5-5  [+1.09s, 1.72s]
```

The agent asked for the wrong file name, the tool failed, and the model answered anyway while claiming the tool showed
something. It was right by prior knowledge, not by evidence. Next time, with a file that is *not* laid out that way,
the same behaviour produces a confident wrong answer with a fake citation.

A trace check catches it without any model judge: every `[tool:X]` in the answer must correspond to a *successful*
`execute_tool X` span. That is `check_evidence_is_real` in the lab, and m2q03 is the only case that fails it.

## Worked example 2: the question that cost 30% of the budget

The trace table for all eight questions (replay mode, synthetic latencies):

```text
case       time llm tools err  in_tok out_tok   cost $
m2q01     3.95s   2     2   0    1500     195   0.0049
m2q02     5.23s   3     3   0    2992     245   0.0084
m2q03     2.81s   2     1   1    1315     120   0.0038
m2q04     4.26s   3     2   0    2751     184   0.0073
m2q05     2.82s   2     1   0    1404     120   0.0040
m2q06     4.19s   3     2   0    2801     179   0.0074
m2q07     3.30s   2     2   0    1509     152   0.0045
m2q08     5.51s   5     4   0    7708     189   0.0173
8 traces, total time 32.07s, total cost $0.0578
```

m2q08 (*"Our podcast app keeps playing during phone calls"*) is one of the easiest questions, yet it costs $0.0173 of
$0.0578, about 30% of the total. The tree shows why: four `search_kb` calls with reworded queries, three of which
returned exactly the same two documents. Input tokens per call climb from 590 to 2,494 because each call resends the
growing conversation. Neither problem is visible in the answer, which is fine.

Two more trace checks catch this pattern: `no_repeat_retrieval` (no two retrievals return the same documents) and
`step_budget` (at most 4 model calls per question).

| Check | Looks at | Passes |
|---|---|---|
| `format` | final answer | 8/8 |
| `evidence_is_real` | answer citations against tool spans | 7/8 (m2q03 fails) |
| `no_repeat_retrieval` | retrieval spans | 7/8 (m2q08 fails) |
| `step_budget` | number of chat spans | 7/8 (m2q08 fails) |

!!! info "About the recorded responses"
    As in module 1, no API key was used to write this module. The model side of each conversation was written by hand,
    but the requests were produced by running the real agent loop against a scripted client, so the recorded
    requests contain the real tool schemas and real tool results. Records are labelled
    `"source": "synthetic-authored"`, and their token counts and latencies come from simple formulas. Re-record with
    your own key (`EVALS_LLM_MODE=record uv run mediadoctor-lab02 run`) to see what Claude actually does; the
    numbers above will change.

## What to trace, as a checklist

- One root span per user request, carrying the request id, prompt version, and final answer.
- One span per model call, with model, tokens, cost, latency, and finish reason.
- One span per tool call, with arguments, a result (or a redacted summary), and error status.
- One span per retrieval, with the query and the ids of what came back. Ids are cheap; full text is optional.
- Status `ERROR` for anything that failed, with a message a human can act on.
- Stable names, so you can group by them. Course-specific facts go under your own prefix.

## Summary

- An agent's answer hides its path. Traces make the path inspectable and checkable.
- Use shared attribute names (OpenTelemetry GenAI conventions) so any backend can read your traces.
- Put tokens, cost, and latency on every model call. The expensive questions are often the easy ones.
- Deterministic tools plus recorded model responses give reproducible traces with no API key.
- Checks over traces catch failures that checks over answers cannot: fabricated evidence, wasted steps.

The [tracing cheat sheet](../../cheatsheets/tracing.md) puts this module on one page.

**Next:** the [lab](lab.md), then [Sending traces to Phoenix, Langfuse, and Braintrust](backends.md).
Sources and influences are listed on the [Credits](../../credits.md) page.
