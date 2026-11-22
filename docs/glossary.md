# Glossary

Seeded in module 1; each later module adds its terms. The module that introduces a term is in brackets.

**Alignment session** [5]
: A regular review of judge-versus-human disagreements with the domain expert, sorting each into judge wrong, label wrong, or criterion unclear, and logging the decisions.

**Analyze, measure, improve** [1]
: The eval loop: find and name failures, build evaluators you trust for them, change the system and verify the change. Then repeat.

**Answer relevance** [7]
: Whether an answer addresses the question that was asked, judged from the question and the answer only. A refusal or an answer about another problem fails.

**Attributes (span attributes)** [2]
: Key-value pairs on a span, such as model name, token counts, or tool arguments. Standard names make them portable across tools.

**Axial coding** [3]
: The second pass of error analysis: grouping open-coding notes into a small set of named failure modes, each with a definition someone else could apply.

**Baseline run** [8]
: A saved run of the configuration that currently ships: every case's outcome per metric, plus the configuration's fingerprint. The gate compares candidates with the baseline committed on the base branch.

**Benevolent dictator** [3]
: The single domain expert who owns pass/fail verdicts and failure-mode definitions, taking input from others but deciding (term used by Hamel Husain).

**BM25 (Okapi BM25)** [7]
: A ranking function for keyword search that weights rare query words more and saturates repeated ones, with a document-length correction. A strong baseline for retrieval.

**Bootstrap (percentile interval)** [5, 6]
: Resampling the data with replacement many times and recomputing a statistic each time; the middle 95% of the results gives an approximate 95% confidence interval.

**Case / test case** [1]
: One input to the system (here, a user question) with an id, plus any metadata needed to evaluate it.

**Case set / dataset** [1]
: A fixed, versioned collection of cases. Comparisons are only meaningful on the same case set.

**Chunking** [7]
: Splitting documents into the passages a retriever indexes, for example fixed-size word windows or one chunk per section. Where boundaries fall decides what can be retrieved together.

**CI budget (eval budget)** [8]
: Limits on what an eval job may cost: replay time per job, and the money and wall time a live re-record of a tier may take. Checked in CI so the suite stays cheap enough to keep running.

**Citation correctness** [7]
: A code check on RAG answers: every cited id was in the retrieved context (valid), and at least one cited passage is relevant to the question (supports).

**Cluster (resampling unit)** [6]
: Outcomes that share a source, such as several runs of one query; resample whole clusters, not their members.

**Code check** [1]
: A deterministic evaluator written as code: an assertion, regex, schema validation, or lookup.

**Code check (validated)** [5]
: A deterministic evaluator measured against human labels like a judge; precise, but its definition can still be narrower than the expert's.

**Compounding failure** [3]
: An early mistake in a multi-step run that causes later symptoms, such as a bad tool argument followed by an answer citing the failed tool. Label the first one.

**Config fingerprint** [8]
: A short hash of everything about the agent's requests except the conversation (model, limits, system prompt, tool definitions). If it changes, every recorded request misses.

**Contamination** [8]
: Eval-case text appearing in something tuned against it (a prompt, a judge's few-shot examples, a knowledge base, or a model's training data), which inflates the score on that case. Found here with shared 8-word runs.

**Context retention** [7]
: In a conversation, using what the user already said. A turn that asks again for a fact the user gave earlier fails it.

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

**Discordant pair** [6]
: A query where two variants disagree: one passes and the other fails. Only these carry information about which variant is better.

**Distinct-n** [4]
: The share of unique n-grams (distinct-1: words, distinct-2: bigrams) in a set of texts; a rough lexical diversity measure that does not measure coverage.

**Eval** [1]
: Any repeatable procedure that measures some aspect of a system's output quality over a set of cases.

**Eval gate (regression gate)** [8]
: A CI check that blocks a merge when a change makes a metric worse beyond chance. Here: paired McNemar tests with a Holm adjustment, a minimum effect, and a warn margin, not a fixed threshold.

**Experiment comparison report** [8]
: A Markdown diff of two runs: what was compared, a per-metric table with paired intervals, the flipped cases to read first, and cost and time. Posted as a CI job summary and uploaded as an artifact.

**Fabricated evidence** [2]
: An answer that cites a tool result, log line, or document the trace shows it never obtained. Detectable with a code check over the trace.

**Failure mode** [1, 3]
: A specific, named way the system goes wrong, for example "drops citations" or "retrieval missed the relevant document".

**Failure taxonomy** [3]
: The list of failure modes for a system with definitions, counts, severity, and priority; kept as a sheet and updated after each round of error analysis.

**Faithfulness (groundedness)** [7]
: Whether every factual claim in an answer is supported by the retrieved context. A true fact from outside the context still fails.

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

**Flaky query** [6]
: A query that passes in some runs and fails in others.

**Golden dataset** [8]
: The fixed cases, labels, and evaluator configs a gate measures against. Versioned, and changed only on purpose.

**Golden manifest** [8]
: A file listing the golden dataset's version, the SHA-256 of each file it consists of, and a digest of each split's case ids. CI fails when the files and the manifest disagree.

**Ground truth / label** [1]
: A human judgment of whether an output is acceptable, made by someone who knows the domain.

**Handoff error** [7]
: Information lost or distorted when one agent passes work to another, such as a planner's brief that drops the file name the user gave.

**Hard negative** [7]
: A passage or example that looks relevant (shared words or topic) but is not. Retrieval and judge test sets need them to avoid overstating quality.

**Held-out rotation** [8]
: Replacing held-out cases with fresh, never-used ones after a set number of looks or a period of time; the old held-out cases join the gate set.

**Held-out split (test split)** [4]
: The part of a dataset kept for occasional reporting and never used for tuning or read while improving the system.

**Holm-Bonferroni adjustment** [6]
: A step-down correction of p-values for multiple tests that controls the chance of any false positive; less blunt than plain Bonferroni.

**Job summary (GitHub Actions)** [8]
: Markdown a workflow step appends to the file named by `$GITHUB_STEP_SUMMARY`; GitHub shows it on the run's summary page.

**Judge leakage** [5]
: Evaluation data reaching the judge prompt: few-shot examples from dev or test, or the expected answer, human verdict, or reviewer note for a case.

**Judge spec** [5]
: The versioned definition of one judge: criterion, PASS and FAIL definitions, context, few-shot examples, and model. Here a TOML file in config/judges/.

**LLM tells** [4]
: Phrasing typical of model-written text ("I'm experiencing", "Could you please", "best practices") that makes synthetic queries unlike real ones.

**LLM-as-judge (model judge)** [1, 5]
: An LLM prompted to grade another model's output against a specific criterion. Trust it only after validating it against labels.

**Margin (gate)** [8]
: The smallest drop you would care about. The gate warns when its interval cannot rule out a drop of that size, even if nothing is significant.

**McNemar's test** [6]
: A paired test that uses only discordant queries (passed by one variant, failed by the other) and asks whether they split more unevenly than a fair coin. The course uses the exact version.

**Minimum detectable difference** [6]
: The smallest change an eval set of a given size can detect at the chosen significance level and power.

**MRR (mean reciprocal rank)** [7]
: The mean over queries of 1 / rank of the first relevant result (0 if none is retrieved).

**Multiple comparisons** [6]
: Running many tests (slices, failure modes, metrics) inflates the chance that at least one looks significant by luck.

**Must-pass case** [8]
: A case that encodes a past incident and is asserted exactly, outside the statistics: any failure blocks.

**nDCG@k** [7]
: Normalised discounted cumulative gain: graded relevance summed with a log2 rank discount over the top k, divided by the same sum for the ideal ranking. 1.0 is a perfect order.

**Near-duplicate** [4]
: Two items whose texts are highly similar without being identical; here measured as Jaccard similarity of word 3-grams.

**Open coding** [3]
: The first pass of error analysis: writing short free-text notes on what went wrong in each trace, without predefined categories.

**OpenInference** [2]
: Arize's set of span attribute conventions for LLM apps, used natively by Phoenix; similar in purpose to the OpenTelemetry GenAI conventions.

**OTLP** [2]
: The OpenTelemetry protocol for sending traces, metrics, and logs to a backend, over HTTP or gRPC, encoded as protobuf or JSON.

**Paired bootstrap** [6]
: A bootstrap that resamples queries while keeping each query's pair of outcomes together, giving an interval for the difference between two variants.

**Paired comparison** [6]
: Running two variants on the same queries and comparing them query by query, which cancels query difficulty and needs far fewer queries.

**Pairwise coverage (all-pairs)** [4]
: A set of tuples in which every feasible pair of values from any two dimensions appears at least once.

**Parent span** [2]
: The span that contains another; parent links turn a flat list of spans into a tree for one trace.

**Pareto chart** [3]
: Bars of failure-mode counts sorted from most to least frequent, with a line for the cumulative share; shows whether a few modes dominate.

**Pass-all rate** [6]
: The share of queries that pass every check; a single headline number that can still be drilled down per failure mode.

**pass@k** [6]
: The chance that at least one of k attempts at a query passes.

**pass^k** [6]
: The chance that all k attempts at a query pass; a measure of consistency for agents.

**Per-case diff** [1]
: The list of cases that changed from pass to fail (broken) or fail to pass (fixed) between two runs.

**Position bias** [5]
: A judge's tendency to prefer the answer in one position when comparing two.

**Power (statistical)** [6]
: The chance that a comparison detects a difference of a given size if it is real; 80% is the usual target.

**Precision@k** [7]
: The share of the top k results that are relevant. Divides by k, so returning fewer results is not rewarded.

**Preflight (replay)** [8]
: Checking that the first request of every case is recorded before running a replayed suite. Catches prompt, model, and tool changes at once; changed tool results surface only in later turns.

**Priority (failure mode)** [3]
: A ranking score for failure modes; in this course, traces affected times severity, with fixability breaking ties.

**Re-record** [8]
: Running the model again in record mode to replace or add fixtures. Done deliberately, for a behaviour change or to check drift, followed by reading and labelling the new outputs; never to make CI pass.

**Recall@k** [7]
: The share of a query's relevant items that appear in the top k results.

**Record / replay / live mode** [1]
: The three `evalkit.llm` modes: call the API and save the response, return saved responses offline, or call without saving.

**Regression** [1]
: A case that passed before a change and fails after it.

**Relevance set** [7]
: Queries paired with labels saying which passages answer each one (optionally graded). The test set for retrieval.

**Replay miss** [8]
: A request with no recorded response. In CI it means the change altered the requests and has to be recorded before it can be evaluated.

**Retrieval failure vs generation failure** [7]
: Attribution of a failed RAG answer: the answering passage never reached the model (retrieval), or it did and the model still answered wrongly or unfaithfully (generation).

**Retrieval miss** [1, 3, 7]
: The retriever did not return the document needed to answer, so downstream steps fail through no fault of their own.

**Root cause (first upstream failure)** [1, 3]
: The earliest step in a run where something went wrong; fixing it often fixes later symptoms.

**Run-to-run variance** [6]
: Variation in outcomes when the same query is run again with nothing changed, from model sampling and the serving stack.

**Seed queries** [4]
: Real user queries used to start or steer synthetic generation: as style examples and as the starting point for coverage, so only gaps are generated.

**Seeded ids** [2]
: Trace and span ids generated from a fixed seed so replayed traces are identical across runs.

**Self-preference (self-enhancement) bias** [5]
: A judge's tendency to rate text from its own model or family more highly.

**Semantic conventions** [2]
: OpenTelemetry's agreed names and meanings for span names and attributes. The GenAI ones (`gen_ai.*`) cover model and tool calls.

**Session-level vs turn-level eval** [7]
: Scoring a whole conversation (did it reach the user's goal, did it give up early) versus scoring each assistant turn (retention, needless questions, format). Session level comes first.

**Severity** [3]
: How much a failure hurts when it happens: 1 annoying, 2 misleading or costly, 3 harmful or trust-breaking. Set by the domain expert.

**Signal (triage flag)** [3]
: A cheap automatic check used to decide which traces to read first. Not a label: flagged traces can pass and unflagged ones can fail.

**Simulated user** [7]
: A model that plays the user in multi-turn evals, with a persona, a goal, and facts it reveals only when asked. It must itself be checked for leaked or invented facts.

**Span** [2]
: One timed unit of work inside a trace (a model call, a tool call, a retrieval), with a name, start and end time, status, and attributes.

**Stale label** [8]
: A label whose output has changed since it was given, for example after a re-record. Found by storing a digest of each labelled output.

**Step efficiency** [7]
: Minimal number of steps for a task divided by the steps a run took (at most 1.0). Shows wasted calls, including in runs that passed.

**Stratified sampling** [4]
: Sampling so that each value of a chosen dimension gets a similar count, instead of leaving small slices to chance.

**Suite tier** [8]
: A part of the eval suite with its own trigger and budget: a fast tier of code checks on every change, a slower judge tier on a schedule or on request.

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

**Trajectory** [7]
: The ordered steps of an agent run: model calls, tool calls with arguments, handoffs, and the final answer. Evaluated after the outcome.

**Transition-failure matrix** [7]
: A count of failed runs by (last state that succeeded, first state that failed). Its hot cells show where a multi-step or multi-agent system breaks first.

**Tuple** [4]
: One combination of values, one per dimension, describing a single test situation before it is written as a query.

**Vanity metric** [6]
: A number that is easy to compute and pleasant to watch but does not track what matters, such as a generic 1-10 helpfulness score or text similarity to a reference.

**Verbosity bias** [5]
: A judge's tendency to prefer longer, more detailed answers regardless of correctness.

**Virtual clock** [2]
: A clock that advances only by recorded or simulated durations, so replayed traces have stable timestamps.

**Vision judge** [7]
: An LLM judge that receives an image (for example a decoded video frame) and returns PASS or FAIL on one visual criterion. Validated like any judge, per artifact and severity.

**Wilson score interval** [6]
: A confidence interval for a pass rate (k of n) that stays inside [0, 1] and behaves at small n and near 0 or 1, unlike p ± 1.96·√(p(1−p)/n).
