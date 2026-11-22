# Glossary

Seeded in module 1; each later module adds its terms. The module that introduces a term is in brackets.

**Alignment session** [5]
: A regular review of judge-versus-human disagreements with the domain expert, sorting each into judge wrong, label wrong, or criterion unclear, and logging the decisions.

**Analyze, measure, improve** [1]
: The eval loop: find and name failures, build evaluators you trust for them, change the system and verify the change. Then repeat.

**Attributes (span attributes)** [2]
: Key-value pairs on a span, such as model name, token counts, or tool arguments. Standard names make them portable across tools.

**Axial coding** [3]
: The second pass of error analysis: grouping open-coding notes into a small set of named failure modes, each with a definition someone else could apply.

**Benevolent dictator** [3]
: The single domain expert who owns pass/fail verdicts and failure-mode definitions, taking input from others but deciding (term used by Hamel Husain).

**Bootstrap (percentile interval)** [5, 6]
: Resampling the data with replacement many times and recomputing a statistic each time; the middle 95% of the results gives an approximate 95% confidence interval.

**Case / test case** [1]
: One input to the system (here, a user question) with an id, plus any metadata needed to evaluate it.

**Case set / dataset** [1]
: A fixed, versioned collection of cases. Comparisons are only meaningful on the same case set.

**Code check (validated)** [5]
: A deterministic evaluator measured against human labels like a judge; precise, but its definition can still be narrower than the expert's.

**Code check** [1]
: A deterministic evaluator written as code: an assertion, regex, schema validation, or lookup.

**Compounding failure** [3]
: An early mistake in a multi-step run that causes later symptoms, such as a bad tool argument followed by an answer citing the failed tool. Label the first one.

**Corrected pass rate (Rogan-Gladen)** [5, 6]
: A judge-measured pass rate adjusted for the judge's TPR and TNR: (observed + TNR − 1) / (TPR + TNR − 1). Defined only when TPR + TNR > 1.

**Cost per trace** [2]
: The summed price of a run's model calls (tokens times per-token price). Divide by successful runs to get cost per successful task.

**Coverage matrix** [4]
: A table of counts for two dimensions (for example topic × evidence), marking combinations excluded by rules and showing real gaps as zeros.

**Covering array** [4]
: A set of test configurations in which every combination of values for any *t* dimensions appears at least once; pairwise coverage is the case *t* = 2.

**Criteria drift** [3, 5]
: The way reviewers' idea of a good or bad output changes as they see more outputs; definitions and earlier labels need revisiting.

**Critique (judge)** [5]
: The short explanation a judge writes before its verdict, quoting the evidence; what you read when the judge and a human disagree.

**Data leakage (split leakage)** [4]
: Test examples that are copies or near-copies of training or dev examples, so tuning on one inflates scores on the other. Prevented by grouping similar items before splitting.

**Dimension (test dimension)** [4]
: One way real inputs differ, such as persona, topic, or expertise, with a few concrete values. Chosen from failure hypotheses.

**Distinct-n** [4]
: The share of unique n-grams (distinct-1: words, distinct-2: bigrams) in a set of texts; a rough lexical diversity measure that does not measure coverage.

**Eval** [1]
: Any repeatable procedure that measures some aspect of a system's output quality over a set of cases.

**Fabricated evidence** [2]
: An answer that cites a tool result, log line, or document the trace shows it never obtained. Detectable with a code check over the trace.

**Failure mode** [1, 3]
: A specific, named way the system goes wrong, for example "drops citations" or "retrieval missed the relevant document".

**Failure taxonomy** [3]
: The list of failure modes for a system with definitions, counts, severity, and priority; kept as a sheet and updated after each round of error analysis.

**False premise** [4]
: A wrong belief stated as fact in a question ("the lumen-l3 has a hardware AV1 decoder"). Tests whether the system checks claims or repeats them.

**Few-shot example (judge)** [5]
: A labelled trace with verdict and critique included in a judge prompt; taken from the train split only.

**Finish reason / stop reason** [2]
: Why the model stopped generating: for Claude, `end_turn` (final answer), `tool_use` (wants a tool), or `max_tokens` (cut off).

**Fixability** [3]
: A rough estimate (easy, medium, hard) of the effort to fix a failure mode; used with priority to pick quick wins.

**Fixture (recorded response)** [1]
: A saved model response, stored under the SHA-256 hash of the exact request, so runs can be replayed offline.

**Ground truth / label** [1]
: A human judgment of whether an output is acceptable, made by someone who knows the domain.

**Held-out split (test split)** [4]
: The part of a dataset kept for occasional reporting and never used for tuning or read while improving the system.

**Judge leakage** [5]
: Evaluation data reaching the judge prompt: few-shot examples from dev or test, or the expected answer, human verdict, or reviewer note for a case.

**Judge spec** [5]
: The versioned definition of one judge: criterion, PASS and FAIL definitions, context, few-shot examples, and model. Here a TOML file in config/judges/.

**LLM tells** [4]
: Phrasing typical of model-written text ("I'm experiencing", "Could you please", "best practices") that makes synthetic queries unlike real ones.

**LLM-as-judge (model judge)** [1, 5]
: An LLM prompted to grade another model's output against a specific criterion. Trust it only after validating it against labels.

**Near-duplicate** [4]
: Two items whose texts are highly similar without being identical; here measured as Jaccard similarity of word 3-grams.

**Open coding** [3]
: The first pass of error analysis: writing short free-text notes on what went wrong in each trace, without predefined categories.

**OpenInference** [2]
: Arize's set of span attribute conventions for LLM apps, used natively by Phoenix; similar in purpose to the OpenTelemetry GenAI conventions.

**OTLP** [2]
: The OpenTelemetry protocol for sending traces, metrics, and logs to a backend, over HTTP or gRPC, encoded as protobuf or JSON.

**Pairwise coverage (all-pairs)** [4]
: A set of tuples in which every feasible pair of values from any two dimensions appears at least once.

**Parent span** [2]
: The span that contains another; parent links turn a flat list of spans into a tree for one trace.

**Pareto chart** [3]
: Bars of failure-mode counts sorted from most to least frequent, with a line for the cumulative share; shows whether a few modes dominate.

**Per-case diff** [1]
: The list of cases that changed from pass to fail (broken) or fail to pass (fixed) between two runs.

**Position bias** [5]
: A judge's tendency to prefer the answer in one position when comparing two.

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

**Seed queries** [4]
: Real user queries used to start or steer synthetic generation: as style examples and as the starting point for coverage, so only gaps are generated.

**Seeded ids** [2]
: Trace and span ids generated from a fixed seed so replayed traces are identical across runs.

**Self-preference (self-enhancement) bias** [5]
: A judge's tendency to rate text from its own model or family more highly.

**Semantic conventions** [2]
: OpenTelemetry's agreed names and meanings for span names and attributes. The GenAI ones (`gen_ai.*`) cover model and tool calls.

**Severity** [3]
: How much a failure hurts when it happens: 1 annoying, 2 misleading or costly, 3 harmful or trust-breaking. Set by the domain expert.

**Signal (triage flag)** [3]
: A cheap automatic check used to decide which traces to read first. Not a label: flagged traces can pass and unflagged ones can fail.

**Span** [2]
: One timed unit of work inside a trace (a model call, a tool call, a retrieval), with a name, start and end time, status, and attributes.

**Stratified sampling** [4]
: Sampling so that each value of a chosen dimension gets a similar count, instead of leaving small slices to chance.

**Synthetic data** [4]
: Test inputs written by a model or by templates rather than by real users. Useful for coverage before launch and for rare cases; not evidence of how often anything happens.

**Theoretical saturation** [3]
: The point where reading more traces no longer reveals new failure modes or changes definitions; the signal to stop an error-analysis round.

**TNR (true negative rate)** [5]
: With PASS as positive: the share of human-failed traces the judge fails. Measures whether the judge catches failures.

**Tool call (tool use)** [2]
: A structured request from the model to run one of the functions you described to it; your code runs it and returns a tool result.

**Tool error recovery** [3]
: An agent fixing a failed tool call (for example retrying with a valid argument) and continuing; the run can still pass.

**TPR (true positive rate)** [5]
: With PASS as positive: the share of human-passed traces the judge passes.

**Trace** [1, 2]
: A structured record of everything one run did: model calls, tool calls, retrieved context, timings, tokens.

**Tuple** [4]
: One combination of values, one per dimension, describing a single test situation before it is written as a query.

**Verbosity bias** [5]
: A judge's tendency to prefer longer, more detailed answers regardless of correctness.

**Virtual clock** [2]
: A clock that advances only by recorded or simulated durations, so replayed traces have stable timestamps.
