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
[tool use documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview):

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
- **Not every stop is an answer.** The loop ends on any `stop_reason` other than `tool_use`, but `max_tokens` (the
  reply was cut off), `refusal` (the model declined), and `pause_turn` (a server-tool turn paused) all end it
  without a complete answer. The agent marks those as `ERROR` on the root span (`evalkit.llm.incomplete_stop`), so
  a truncated reply is never graded as if it were finished. Thinking makes `max_tokens` easy to hit: Sonnet 5.5 and
  Haiku 5.5 think by default, and thinking counts toward the limit. The course sets thinking and effort explicitly
  for each model in `config/models.toml` (`[generation.<model>]`), and `evalkit.LLM` adds them to every request, so
  they are part of the recorded request, its replay key, and its trace.

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

## Worked example 1: does the answer's evidence exist?

Question m2q03: *"progressive_late_moov.mp4 takes about 10 seconds to start over HTTP but plays fine once it starts.
Why?"* The answer:

```text
Likely cause: The MP4's top-level box order is ftyp, free, mdat, moov, so the moov index is at the end of the
file. ...
Next step: Remux with the index at the front: ffmpeg -i progressive_late_moov.mp4 -c copy -movflags +faststart ...
Sources: [tool:ffprobe] [kb:mp4-faststart]
```

It is well formatted and technically plausible, so a module 1 style check passes it. But a format check cannot tell
whether the answer *saw* that box order or only claims to. The trace can:

```text
invoke_agent MediaDoctor  [+0ms, 4.49s]
├─ chat claude-sonnet-5-5  [+0ms, 1.96s]
├─ execute_tool ffprobe  [+1.96s, 45ms]
│      · gen_ai.tool.call.arguments = {"file": "progressive_late_moov.mp4"}
│      · gen_ai.tool.call.result = {"bit_rate": 732132, "duration_s": 2.0, "file": "progressive_late_moov.mp4", ...
├─ execute_tool search_kb  [+2.00s, 10ms]
│  └─ retrieval  [+2.00s, 6ms]
│         · mediadoctor.retrieval.doc_ids = ["mp4-faststart", "widevine-levels"]
└─ chat claude-sonnet-5-5  [+2.01s, 2.48s]
```

The agent asked for the right file, the ffprobe span succeeded, and its result contains
`"mp4_top_level_boxes": ["ftyp", "free", "mdat", "moov"]`, exactly what the answer quotes. The citation is backed by
evidence.

The failure this guards against is the near miss: an agent that asks for `late_moov.mp4`, gets
`media file not found: 'late_moov.mp4'. Available: ...` back as an `ERROR` span, and answers "ffprobe shows the moov
atom is at the end" anyway. That answer could even be right by prior knowledge, and the next time, with a file that is
*not* laid out that way, the same behaviour produces a confident wrong answer with a fake citation. A trace check
catches it without any model judge: every `[tool:X]` in the answer must correspond to a *successful*
`execute_tool X` span. That is `check_evidence_is_real` in the lab. In the recorded runs no tool call fails and all
eight cases pass it; the lab tests also run it on a copy of the m2q03 trace with the ffprobe span marked `ERROR`,
where it fails as it should.

## Worked example 2: where the time and money go

The trace table for all eight questions (replay mode, modelled latencies):

```text
case       time llm tools err  in_tok out_tok   cost $
m2q01     7.01s   2     3   0    2070     247   0.0066
m2q02     6.56s   2     3   0    2118     292   0.0072
m2q03     4.49s   2     2   0    1917     204   0.0059
m2q04     6.25s   2     3   0    2097     286   0.0071
m2q05    12.48s   2     2   0    1953     217   0.0061
m2q06     8.86s   2     2   0    2096     244   0.0066
m2q07     4.84s   2     2   0    1604     209   0.0053
m2q08     6.78s   2     1   0    1930     200   0.0059
8 traces, total time 57.27s, total cost $0.0506
```

Every case follows the same shape: one model call that requests all the tools it wants at once, then one model call
that answers. Costs are flat, from $0.0053 (m2q07, 10.5% of the total) to $0.0072 (m2q02, 14.2%), with no question
standing out. Two things are still only visible in the trace:

- **Input tokens double on the second call.** In m2q08 (*"Our podcast app keeps playing during phone calls"*) the
  first call sends 620 input tokens and the second 1,310, although the agent only ran one search: each call resends
  the system prompt, the tool schemas, and the whole conversation, including every tool result. An agent that loops,
  rewording the same search four times, would pay that growing price on every step.
- **Latency is model time.** Tool spans take 2 to 45 ms; the model calls take the rest. m2q05 is the slowest trace at
  12.48 s because its second call took 9.43 s for 136 output tokens: a slow-tail latency (the recorded latencies
  are modelled, including an occasional slow call), not extra work. Without the per-span timings you would not know
  which.

Two more trace checks catch the looping pattern: `no_repeat_retrieval` (no two retrievals return the same documents)
and `step_budget` (at most 4 model calls per question).

| Check | Looks at | Passes |
|---|---|---|
| `format` | final answer | 8/8 |
| `evidence_is_real` | answer citations against tool spans | 8/8 |
| `no_repeat_retrieval` | retrieval spans | 8/8 |
| `step_budget` | number of chat spans | 8/8 |

All four checks pass on all eight recorded traces, so here they confirm the path was clean rather than find a
failure. That is still worth having: the checks are code, they run on every future run, and on data where the agent
does misbehave (a wrong file name, a retrieval loop) they flag the case without anyone reading the trace. Module 3
turns this kind of reading into a systematic error analysis.

!!! info "About the recorded responses"
    As in module 1, no API key was used to write this module. The model side of each conversation was generated by
    Claude subagents standing in for the model, and the requests were produced by running the real agent loop, so
    the recorded requests contain the real tool schemas and real tool results. Records are labelled
    `"source": "subagent-authored"`, and their token counts and latencies come from simple formulas (tokens are
    characters / 4; latency is modelled, with an occasional slow tail). Re-record with your own key
    (`EVALS_LLM_MODE=record uv run mediadoctor-lab02 run`) to see what Claude actually does; the numbers above will
    change.

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
- Put tokens, cost, and latency on every model call. Input tokens grow with every step, and latency is mostly
  model time.
- Deterministic tools plus recorded model responses give reproducible traces with no API key.
- Checks over traces catch failures that checks over answers cannot: fabricated evidence, wasted steps. On clean
  runs, like the recorded ones here, they confirm the path rather than flag it.

The [tracing cheat sheet](../../cheatsheets/tracing.md) puts this module on one page.

**Next:** the [lab](lab.md), then [Sending traces to Phoenix, Langfuse, and Braintrust](backends.md).
Sources and influences are listed on the [Credits](../../credits.md) page.
