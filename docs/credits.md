# Credits

This course is original work: the text, code, datasets, knowledge-base notes, and recorded fixtures were written
for it. Its overall arc and several core ideas come from the work of **Hamel Husain** and **Shreya Shankar**, and
anyone serious about evals should read them directly and consider their course.

## Where ideas come from

| Idea used here | Where it is used | Source |
|---|---|---|
| Course arc: build a measurable agent, error analysis, evaluators you trust, CI/CD, red-teaming, improving cost and accuracy | Whole course | [AI Evals For Engineers & PMs](https://maven.com/parlance-labs/evals) (Maven course by Hamel Husain and Shreya Shankar) |
| The analyze, measure, improve cycle | Module 1 onward | Hamel Husain and Shreya Shankar's course and [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) |
| Layering evaluators from cheap assertions up to human and model review | Module 1 | [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/), Hamel Husain |
| Looking at your data first; error analysis before metrics; custom data viewers | Modules 1, 3, 9 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Binary pass/fail judges aligned with a domain expert | Modules 1, 5 | [Using LLM-as-a-Judge For Evaluation](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain |
| Open coding then axial coding of traces; theoretical saturation; noting the first failure in a trace; reviewing at least 100 traces; a single domain expert as "benevolent dictator"; binary pass/fail verdicts | Module 3 | [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/), Hamel Husain and Shreya Shankar, and their [Maven course](https://maven.com/parlance-labs/evals) |
| Error analysis as the highest-return activity; bottom-up categories from your own data | Module 3 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Synthetic queries from dimensions and tuples: start from failure hypotheses, write tuples by hand first, generate tuples and natural-language queries in two separate steps; synthetic data cannot tell you how common a failure is, and compare with real data as soon as it exists | Module 4 | [AI Evals FAQ: What is the best approach for generating synthetic data?](https://hamel.dev/blog/posts/evals-faq/what-is-the-best-approach-for-generating-synthetic-data.html), Hamel Husain and Shreya Shankar |
| Where synthetic data is unreliable (specialised domains, high stakes, cases you cannot validate) | Module 4 | [AI Evals FAQ: Are there scenarios where synthetic data may not be reliable?](https://hamel.dev/blog/posts/evals-faq/are-there-scenarios-where-synthetic-data-may-not-be-reliable.html), Hamel Husain and Shreya Shankar |
| Criteria drift: reviewers' criteria change as they see outputs | Modules 3, 5 | Shreya Shankar et al., [Who Validates the Validators?](https://arxiv.org/abs/2404.12272) |
| One judge per failure mode; binary pass/fail rather than 1 to 5 scales; aim for 50+ passes and 50+ failures when validating; what to do when a judge will not agree with reviewers | Module 5 | [AI Evals FAQ: binary vs Likert](https://hamel.dev/blog/posts/evals-faq/why-do-you-recommend-binary-passfail-evaluations-instead-of-1-5-ratings-likert-scales.html), [How much of a trace should I give an LLM judge?](https://hamel.dev/blog/posts/evals-faq/how-much-of-a-trace-should-i-give-an-llm-judge.html), [When I can't get my LLM judge to agree with human reviewers](https://hamel.dev/blog/posts/evals-faq/what-should-i-do-when-i-cant-get-my-llm-judge-to-agree-with-human-reviewers.html), Hamel Husain and Shreya Shankar |
| Critique before verdict; iterating with a domain expert; few-shot examples from labelled data | Module 5 | [Using LLM-as-a-Judge For Evaluation](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain |
| Train/dev/test splits for judges; TPR and TNR; correcting a judge-measured pass rate with a bootstrap interval | Module 5 | Hamel Husain and Shreya Shankar's [Maven course](https://maven.com/parlance-labs/evals) and their open-source [judgy](https://github.com/ai-evals-course/judgy) library (the code here is an independent implementation) |
| Every metric gets an interval; paired comparisons; clustered resampling; power analysis for evals | Module 6 | Evan Miller, [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) (arXiv 2411.00640) |
| A pass-all rate with drill-down instead of a weighted composite; generic metrics and similarity scores are not quality measures | Module 6 | [How do I combine my evals into a single metric?](https://hamel.dev/blog/posts/evals-faq/how-do-i-combine-my-evals-into-a-single-metric.html), [Should I use "ready-to-use" evaluation metrics?](https://hamel.dev/blog/posts/evals-faq/should-i-use-ready-to-use-evaluation-metrics.html), [Are similarity metrics useful?](https://hamel.dev/blog/posts/evals-faq/are-similarity-metrics-bertscore-rouge-etc-useful-for-evaluating-llm-outputs.html), Hamel Husain and Shreya Shankar |
| Judge-error correction, bootstrap intervals, and paired tests as part of an evals curriculum | Modules 5, 6 | Hamel Husain and Shreya Shankar's [Maven course](https://maven.com/parlance-labs/evals) |
| Instrument first; build simple custom viewers for traces | Module 2 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Validating evaluators against human labels; criteria drift | Modules 5, 6 | Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://arxiv.org/abs/2404.12272) (arXiv 2404.12272) |

## Module 6 references

| Topic | Source |
|---|---|
| Wilson score interval and alternatives | [Binomial proportion confidence interval](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval) (Wilson, 1927) |
| Bootstrap | [Bootstrapping (statistics)](https://en.wikipedia.org/wiki/Bootstrapping_(statistics)) (Efron, 1979) |
| McNemar's test | [McNemar's test](https://en.wikipedia.org/wiki/McNemar%27s_test) (McNemar, 1947) |
| Sample size for paired proportions | Connor, [Sample size for testing differences in proportions for the paired-sample design](https://pubmed.ncbi.nlm.nih.gov/3567305/), Biometrics, 1987 |
| Power | [Power (statistics)](https://en.wikipedia.org/wiki/Power_(statistics)) |
| Multiple comparisons; Holm-Bonferroni | [Multiple comparisons problem](https://en.wikipedia.org/wiki/Multiple_comparisons_problem), [Holm-Bonferroni method](https://en.wikipedia.org/wiki/Holm%E2%80%93Bonferroni_method) (Holm, 1979) |
| pass@k unbiased estimator | Chen et al., [Evaluating Large Language Models Trained on Code](https://arxiv.org/abs/2107.03374) (arXiv 2107.03374) |
| pass^k | Yao et al., [τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains](https://arxiv.org/abs/2406.12045) (arXiv 2406.12045) |
| Temperature and determinism on Claude | [Anthropic: Messages API reference](https://platform.claude.com/docs/en/api/messages) (the `temperature` parameter) |
| Nondeterminism in LLM serving | Horace He and Thinking Machines Lab, [Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) |

The module 6 runs (agent prompt v2, and repeats of both prompts), their labels, the reference answers, and the
helpfulness judge's scores are synthetic-authored for this course (`scripts/author_module06_fixtures.py`,
`data/labels/module06_runs.csv`, `data/labels/module06_reference_answers.csv`). They were not produced by running
the models live.

## Module 5 references

| Topic | Source |
|---|---|
| Correcting prevalence for test error | Rogan and Gladen, [Estimating prevalence from the results of a screening test](https://pubmed.ncbi.nlm.nih.gov/623091/), American Journal of Epidemiology, 1978 |
| Sensitivity and specificity (TPR and TNR) | [Sensitivity and specificity](https://en.wikipedia.org/wiki/Sensitivity_and_specificity) |
| Bootstrap confidence intervals | [Bootstrapping (statistics)](https://en.wikipedia.org/wiki/Bootstrapping_(statistics)) |
| Position, verbosity, and self-enhancement bias in LLM judges | Zheng et al., [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) (arXiv 2306.05685) |
| Self-preference in LLM evaluators | Panickssery et al., [LLM Evaluators Recognize and Favor Their Own Generations](https://arxiv.org/abs/2404.13076) (arXiv 2404.13076) |
| Criteria drift | Shankar et al., [Who Validates the Validators?](https://arxiv.org/abs/2404.12272) (arXiv 2404.12272) |

The module 5 traces, reference labels, judge specs, and recorded judge outputs (including the judges' mistakes)
are synthetic-authored for this course (`scripts/author_module05_fixtures.py`, `config/judges/`,
`data/labels/module05_reference.csv`). They were not produced by running the models live.

## Module 4 references

| Topic | Source |
|---|---|
| Pairwise (all-pairs) testing and covering arrays | [All-pairs testing](https://en.wikipedia.org/wiki/All-pairs_testing) |
| Shingles and Jaccard similarity for near-duplicates | [w-shingling](https://en.wikipedia.org/wiki/W-shingling), [Jaccard index](https://en.wikipedia.org/wiki/Jaccard_index) |
| Distinct-n diversity | Li et al., [A Diversity-Promoting Objective Function for Neural Conversation Models](https://arxiv.org/abs/1510.03055) (arXiv 1510.03055) |
| Message Batches API | [Anthropic: batch processing](https://docs.anthropic.com/en/docs/build-with-claude/batch-processing) |

The dimensions, rules, beta queries, generated queries, dataset v1, the template query writer, and the dev-slice
traces and reference labels are synthetic-authored for this course (`config/synth/`, `data/synth/`,
`scripts/module04_writer.py`, `scripts/author_module04_fixtures.py`).

## Module 3 references

| Topic | Source |
|---|---|
| Open, axial coding and theoretical saturation (origin in qualitative research) | [Grounded theory](https://en.wikipedia.org/wiki/Grounded_theory) (overview; the method goes back to Glaser and Strauss, 1967) |
| Pareto charts | [Pareto chart](https://en.wikipedia.org/wiki/Pareto_chart) |

The module 3 traces, scenarios, and reference annotations are synthetic-authored for this course
(`scripts/author_module03_fixtures.py`, `data/labels/`).

## Module 2 references

| Topic | Source |
|---|---|
| Tool use with Claude (the agent loop) | [Anthropic: tool use overview](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) |
| Span and attribute names (`gen_ai.*`) | [OpenTelemetry semantic conventions for generative AI](https://github.com/open-telemetry/semantic-conventions-genai) (status: development) |
| OTLP/JSON encoding | [OpenTelemetry protocol specification](https://opentelemetry.io/docs/specs/otlp/) |
| OpenInference attributes | [OpenInference](https://github.com/Arize-ai/openinference) (Arize) |
| Phoenix ingestion | [Phoenix: exporter and OTLP](https://arize.com/docs/phoenix/tracing/concepts-tracing/otel-openinference/exporter) |
| Langfuse ingestion | [Langfuse: OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry) |
| Braintrust ingestion | [Braintrust: send OpenTelemetry traces](https://docs.braintrust.dev/integrations/sdk-integrations/opentelemetry/send-traces-and-logs) |
| Sample clips | Generated with [FFmpeg](https://ffmpeg.org/) test sources (`scripts/make_media.sh`); probed with ffprobe |

The two devices in `data/devices/` and the logs in `data/logs/` are fictional and written for this course.

This course is independent and is not affiliated with or endorsed by Hamel Husain, Shreya Shankar, Parlance Labs,
Maven, or Anthropic.

## Tools

[uv](https://docs.astral.sh/uv/), [Zensical](https://zensical.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), [pytest](https://pytest.org/), [FFmpeg](https://ffmpeg.org/),
[Ruff](https://docs.astral.sh/ruff/), [gitleaks](https://github.com/gitleaks/gitleaks), and the
[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
