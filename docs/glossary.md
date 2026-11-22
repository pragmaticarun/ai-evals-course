# Glossary

Seeded in module 1; each later module adds its terms. The module that introduces a term is in brackets.

**Analyze, measure, improve** [1]
: The eval loop: find and name failures, build evaluators you trust for them, change the system and verify the change. Then repeat.

**Attributes (span attributes)** [2]
: Key-value pairs on a span, such as model name, token counts, or tool arguments. Standard names make them portable across tools.

**Axial coding** [3]
: The second pass of error analysis: grouping open-coding notes into a small set of named failure modes, each with a definition someone else could apply.

**Benevolent dictator** [3]
: The single domain expert who owns pass/fail verdicts and failure-mode definitions, taking input from others but deciding (term used by Hamel Husain).

**Case / test case** [1]
: One input to the system (here, a user question) with an id, plus any metadata needed to evaluate it.

**Case set / dataset** [1]
: A fixed, versioned collection of cases. Comparisons are only meaningful on the same case set.

**Code check** [1]
: A deterministic evaluator written as code: an assertion, regex, schema validation, or lookup.

**Compounding failure** [3]
: An early mistake in a multi-step run that causes later symptoms, such as a bad tool argument followed by an answer citing the failed tool. Label the first one.

**Cost per trace** [2]
: The summed price of a run's model calls (tokens times per-token price). Divide by successful runs to get cost per successful task.

**Criteria drift** [3, 5]
: The way reviewers' idea of a good or bad output changes as they see more outputs; definitions and earlier labels need revisiting.

**Eval** [1]
: Any repeatable procedure that measures some aspect of a system's output quality over a set of cases.

**Fabricated evidence** [2]
: An answer that cites a tool result, log line, or document the trace shows it never obtained. Detectable with a code check over the trace.

**Failure mode** [1, 3]
: A specific, named way the system goes wrong, for example "drops citations" or "retrieval missed the relevant document".

**Failure taxonomy** [3]
: The list of failure modes for a system with definitions, counts, severity, and priority; kept as a sheet and updated after each round of error analysis.

**Finish reason / stop reason** [2]
: Why the model stopped generating: for Claude, `end_turn` (final answer), `tool_use` (wants a tool), or `max_tokens` (cut off).

**Fixability** [3]
: A rough estimate (easy, medium, hard) of the effort to fix a failure mode; used with priority to pick quick wins.

**Fixture (recorded response)** [1]
: A saved model response, stored under the SHA-256 hash of the exact request, so runs can be replayed offline.

**Ground truth / label** [1]
: A human judgment of whether an output is acceptable, made by someone who knows the domain.

**LLM-as-judge (model judge)** [1, 5]
: An LLM prompted to grade another model's output against a specific criterion. Trust it only after validating it against labels.

**Open coding** [3]
: The first pass of error analysis: writing short free-text notes on what went wrong in each trace, without predefined categories.

**OpenInference** [2]
: Arize's set of span attribute conventions for LLM apps, used natively by Phoenix; similar in purpose to the OpenTelemetry GenAI conventions.

**OTLP** [2]
: The OpenTelemetry protocol for sending traces, metrics, and logs to a backend, over HTTP or gRPC, encoded as protobuf or JSON.

**Parent span** [2]
: The span that contains another; parent links turn a flat list of spans into a tree for one trace.

**Pareto chart** [3]
: Bars of failure-mode counts sorted from most to least frequent, with a line for the cumulative share; shows whether a few modes dominate.

**Per-case diff** [1]
: The list of cases that changed from pass to fail (broken) or fail to pass (fixed) between two runs.

**Priority (failure mode)** [3]
: A ranking score for failure modes; in this course, traces affected times severity, with fixability breaking ties.

**Record / replay / live mode** [1]
: The three `evalkit.llm` modes: call the API and save the response, return saved responses offline, or call without saving.

**Regression** [1]
: A case that passed before a change and fails after it.

**Retrieval miss** [1, 3, 7]
: The retriever did not return the document needed to answer, so downstream steps fail through no fault of their own.

**Root cause (first upstream failure)** [1, 3]
: The earliest step in a run where something went wrong; fixing it often fixes later symptoms.

**Seeded ids** [2]
: Trace and span ids generated from a fixed seed so replayed traces are identical across runs.

**Semantic conventions** [2]
: OpenTelemetry's agreed names and meanings for span names and attributes. The GenAI ones (`gen_ai.*`) cover model and tool calls.

**Severity** [3]
: How much a failure hurts when it happens: 1 annoying, 2 misleading or costly, 3 harmful or trust-breaking. Set by the domain expert.

**Signal (triage flag)** [3]
: A cheap automatic check used to decide which traces to read first. Not a label: flagged traces can pass and unflagged ones can fail.

**Span** [2]
: One timed unit of work inside a trace (a model call, a tool call, a retrieval), with a name, start and end time, status, and attributes.

**Theoretical saturation** [3]
: The point where reading more traces no longer reveals new failure modes or changes definitions; the signal to stop an error-analysis round.

**Tool call (tool use)** [2]
: A structured request from the model to run one of the functions you described to it; your code runs it and returns a tool result.

**Tool error recovery** [3]
: An agent fixing a failed tool call (for example retrying with a valid argument) and continuing; the run can still pass.

**Trace** [1, 2]
: A structured record of everything one run did: model calls, tool calls, retrieved context, timings, tokens.

**Virtual clock** [2]
: A clock that advances only by recorded or simulated durations, so replayed traces have stable timestamps.
