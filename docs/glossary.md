# Glossary

Seeded in module 1; each later module adds its terms. The module that introduces a term is in brackets.

**Analyze, measure, improve** [1]
: The eval loop: find and name failures, build evaluators you trust for them, change the system and verify the change. Then repeat.

**Attributes (span attributes)** [2]
: Key-value pairs on a span, such as model name, token counts, or tool arguments. Standard names make them portable across tools.

**Case / test case** [1]
: One input to the system (here, a user question) with an id, plus any metadata needed to evaluate it.

**Case set / dataset** [1]
: A fixed, versioned collection of cases. Comparisons are only meaningful on the same case set.

**Code check** [1]
: A deterministic evaluator written as code: an assertion, regex, schema validation, or lookup.

**Cost per trace** [2]
: The summed price of a run's model calls (tokens times per-token price). Divide by successful runs to get cost per successful task.

**Eval** [1]
: Any repeatable procedure that measures some aspect of a system's output quality over a set of cases.

**Fabricated evidence** [2]
: An answer that cites a tool result, log line, or document the trace shows it never obtained. Detectable with a code check over the trace.

**Failure mode** [1]
: A specific, named way the system goes wrong, for example "drops citations" or "retrieval missed the relevant document".

**Finish reason / stop reason** [2]
: Why the model stopped generating: for Claude, `end_turn` (final answer), `tool_use` (wants a tool), or `max_tokens` (cut off).

**Fixture (recorded response)** [1]
: A saved model response, stored under the SHA-256 hash of the exact request, so runs can be replayed offline.

**Ground truth / label** [1]
: A human judgment of whether an output is acceptable, made by someone who knows the domain.

**LLM-as-judge (model judge)** [1, 5]
: An LLM prompted to grade another model's output against a specific criterion. Trust it only after validating it against labels.

**OpenInference** [2]
: Arize's set of span attribute conventions for LLM apps, used natively by Phoenix; similar in purpose to the OpenTelemetry GenAI conventions.

**OTLP** [2]
: The OpenTelemetry protocol for sending traces, metrics, and logs to a backend, over HTTP or gRPC, encoded as protobuf or JSON.

**Parent span** [2]
: The span that contains another; parent links turn a flat list of spans into a tree for one trace.

**Per-case diff** [1]
: The list of cases that changed from pass to fail (broken) or fail to pass (fixed) between two runs.

**Record / replay / live mode** [1]
: The three `evalkit.llm` modes: call the API and save the response, return saved responses offline, or call without saving.

**Regression** [1]
: A case that passed before a change and fails after it.

**Retrieval miss** [1, 7]
: The retriever did not return the document needed to answer, so downstream steps fail through no fault of their own.

**Root cause (first upstream failure)** [1, 3]
: The earliest step in a run where something went wrong; fixing it often fixes later symptoms.

**Seeded ids** [2]
: Trace and span ids generated from a fixed seed so replayed traces are identical across runs.

**Semantic conventions** [2]
: OpenTelemetry's agreed names and meanings for span names and attributes. The GenAI ones (`gen_ai.*`) cover model and tool calls.

**Span** [2]
: One timed unit of work inside a trace (a model call, a tool call, a retrieval), with a name, start and end time, status, and attributes.

**Tool call (tool use)** [2]
: A structured request from the model to run one of the functions you described to it; your code runs it and returns a tool result.

**Trace** [1, 2]
: A structured record of everything one run did: model calls, tool calls, retrieved context, timings, tokens.

**Virtual clock** [2]
: A clock that advances only by recorded or simulated durations, so replayed traces have stable timestamps.
