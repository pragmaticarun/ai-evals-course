# Cheat sheets

One cheat sheet per module, and the rules from all of them on one page. Print this page; open a sheet when you need
its commands and formulas.

| Module | Cheat sheet | Open it when you are... |
|---|---|---|
| 1 | [The eval loop](eval-loop.md) | starting on a new LLM product and deciding what to measure first |
| 2 | [Tracing an agent](tracing.md) | instrumenting an agent: spans, attributes, tokens, cost |
| 3 | [Error analysis](error-analysis.md) | reading traces and building a failure taxonomy |
| 4 | [Synthetic data](synthetic-data.md) | generating test queries from dimensions and tuples |
| 5 | [Judges and validation](judges.md) | choosing between a code check and a judge, and validating a judge |
| 6 | [Statistics for metrics](stats.md) | putting intervals on numbers, comparing two versions, sizing a test set |
| 7 | [Evaluating architectures](architectures.md) | evaluating RAG, multi-turn chat, multi-agent systems, or vision |
| 8 | [CI/CD for evals](ci-cd.md) | gating pull requests and keeping a golden set honest |
| 9 | [Monitoring and annotation](monitoring.md) | watching production, sampling traces for review, measuring agreement |
| 10 | [Red-team checklist](red-team.md) | testing prompt injection and unsafe tool use |
| 11 | [Cost and latency](cost-latency.md) | running experiments on accuracy, latency, and cost |
| 12 | [Writing the eval report](eval-report.md) | turning all of the above into a decision |

## The rules on one page

**The loop (1).** Analyze, measure, improve, repeat. Look at data before choosing metrics. Code checks first, judges
for what code cannot see, people for discovery and labels.

**Tracing (2).** One span per model call, tool call, and retrieval; tokens, cost, and latency on every model span;
`ERROR` status with a message a person can act on. Use the OpenTelemetry GenAI attribute names.

**Error analysis (3).** Read about 100 traces. Write what went wrong in plain words (open coding), group the notes
into modes (axial coding), label the first upstream failure, count, rank by frequency × severity, and stop at
saturation. One domain expert owns the labels.

**Synthetic data (4).** Dimensions from failure hypotheses; tuples by hand first, then generated; queries from
tuples in a separate step; check, deduplicate, split. Synthetic data finds failures; it cannot tell you how common
they are.

**Judges (5).** One binary judge per failure mode. Validate on train, dev, and test splits of human labels; report
TPR and TNR, not accuracy. Correct judge-measured rates for judge error, with a bootstrap interval.

**Statistics (6).** Every rate gets a Wilson interval and a denominator. Compare versions paired on the same cases,
with fixed and broken counts (McNemar). Know the smallest difference your set can detect before you run.

**Architectures (7).** Score each component on its own labels (recall@k, faithfulness, handoffs), keep the
end-to-end outcome as the headline, and attribute each failure to the first component that broke.

**CI/CD (8).** Replay in CI: fast, deterministic, free. Gate on paired regressions with a written rule. Version the
golden set with a manifest; read the held-out split only for releases, and log every look.

**Monitoring (9).** Free checks on all traffic, judges on a sample, people on a weighted queue that always includes
random traces. Control charts and CUSUM for alarms; segment by version before you blame the model.

**Red-teaming (10).** Every tool output is untrusted input. Measure attack success and benign false positives
together. Make dangerous actions impossible in code (allow-lists, approvals), not just unlikely in the prompt.

**Improving (11).** Choose fixes by expected value. Change one thing at a time; pre-register the metric and the
rule; report success with an interval, p50 and p95 latency, and cost per successful task.

**Reporting (12).** Decision first, three numbers with intervals, validated evaluators, risks that would change the
decision, and an appendix that reproduces everything.
