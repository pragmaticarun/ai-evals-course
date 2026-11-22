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
| Evaluate retrieval with search metrics (recall@k, precision@k, MRR) on query-passage pairs, separately from generation; generation judged for context use and answer relevance with validated judges | Module 7 | [AI Evals FAQ: How should I approach evaluating my RAG system?](https://hamel.dev/blog/posts/evals-faq/how-should-i-approach-evaluating-my-rag-system.html), Hamel Husain and Shreya Shankar |
| Question, context, and answer relationships as the RAG evals (context relevance, faithfulness, answer relevance) | Module 7 | Jason Liu, [There Are Only 6 RAG Evals](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/) |
| Chunk size as a task-dependent choice to test | Module 7 | [AI Evals FAQ: How do I choose the right chunk size?](https://hamel.dev/blog/posts/evals-faq/how-do-i-choose-the-right-chunk-size-for-my-document-processing-tasks.html), Hamel Husain and Shreya Shankar |
| Whole-conversation pass/fail first, then the first upstream failure; reduce to a single-turn test; simulated users and N−1 testing | Module 7 | [AI Evals FAQ: How do I debug multi-turn conversation traces?](https://hamel.dev/blog/posts/evals-faq/how-do-i-debug-multi-turn-conversation-traces.html), Hamel Husain and Shreya Shankar |
| Outcome first, then the steps of an agent's trajectory | Module 7 | [AI Evals FAQ: How do I evaluate agentic workflows?](https://hamel.dev/blog/posts/evals-faq/how-do-i-evaluate-agentic-workflows.html), Hamel Husain and Shreya Shankar |
| Transition-failure matrices (last successful state vs first failure); outcome and process metrics by workflow stage | Module 7 | [AI Evals FAQ: How do I evaluate complex multi-step workflows?](https://hamel.dev/blog/posts/evals-faq/how-do-i-evaluate-complex-multi-step-workflows.html), Hamel Husain and Shreya Shankar |
| CI evals are small, purpose-built sets (core features, past bugs, edge cases) that favour deterministic checks over judges; production monitoring feeds new cases back into CI | Module 8 | [AI Evals FAQ: How are evaluations used differently in CI/CD vs. monitoring production?](https://hamel.dev/blog/posts/evals-faq/how-are-evaluations-used-differently-in-cicd-vs-monitoring-production.html), Hamel Husain and Shreya Shankar |
| Gold datasets go stale and need refreshing through error analysis; weigh each eval's cost against its signal | Module 8 | [AI Evals FAQ: What should I do when my "gold" eval dataset becomes stale?](https://hamel.dev/blog/posts/evals-faq/what-should-i-do-when-my-gold-eval-dataset-becomes-stale.html), Hamel Husain and Shreya Shankar |
| Train, dev, and test sets for evaluators; repeated use of dev results overfits even without copying examples; a test set kept for a final check | Modules 5, 8 | [AI Evals FAQ: How do I know if I can trust my automated eval?](https://hamel.dev/blog/posts/evals-faq/how-do-i-know-if-i-can-trust-my-automated-eval.html), Hamel Husain and Shreya Shankar |
| Cheap assertions on every code change, more expensive evaluations on a slower cadence | Modules 1, 8 | [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/), Hamel Husain |
| Build a custom annotation tool; render traces for the domain, show progress, use hotkeys, keep the review in flow | Module 9 | [AI Evals FAQ: Should I build a custom annotation tool?](https://hamel.dev/blog/posts/evals-faq/should-i-build-a-custom-annotation-tool-or-use-something-off-the-shelf.html) and [What makes a good custom interface for reviewing LLM outputs?](https://hamel.dev/blog/posts/evals-faq/what-makes-a-good-custom-interface-for-reviewing-llm-outputs.html), Hamel Husain and Shreya Shankar |
| Sampling production traces from exploratory to targeted (random, clustering, data analysis, classification, feedback), keeping random traces in every batch | Module 9 | [AI Evals FAQ: How can I efficiently sample production traces for review?](https://hamel.dev/blog/posts/evals-faq/how-can-i-efficiently-sample-production-traces-for-review.html), Hamel Husain and Shreya Shankar |
| Surfacing problem traces beyond user feedback: random samples, existing evals as screens, outliers and stratification | Module 9 | [AI Evals FAQ: How do I surface problematic traces for review beyond user feedback?](https://hamel.dev/blog/posts/evals-faq/how-do-i-surface-problematic-traces-for-review-beyond-user-feedback.html), Hamel Husain and Shreya Shankar |
| Cohen's kappa when more than one person annotates; label independently, then resolve disagreements by updating the rubric | Module 9 | [AI Evals FAQ: How many people should annotate my LLM outputs?](https://hamel.dev/blog/posts/evals-faq/how-many-people-should-annotate-my-llm-outputs.html), Hamel Husain and Shreya Shankar |
| Re-running error analysis after changes and incidents, with small regular reviews of flagged traces in between | Module 9 | [AI Evals FAQ: How often should I re-run error analysis on my production system?](https://hamel.dev/blog/posts/evals-faq/how-often-should-i-re-run-error-analysis-on-my-production-system.html), Hamel Husain and Shreya Shankar |
| Instrument first; build simple custom viewers for traces | Modules 2, 9 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Validating evaluators against human labels; criteria drift | Modules 5, 6, 9 | Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://arxiv.org/abs/2404.12272) (arXiv 2404.12272) |
| Guardrails sit inline and block clear failures before users see them (so their false positives are production bugs: version the rules, log triggers, monitor rates); evaluators measure afterwards; never use off-the-shelf LLM guardrails without reading their prompts | Module 10 | [AI Evals FAQ: What's the difference between guardrails & evaluators?](https://hamel.dev/blog/posts/evals-faq/whats-the-difference-between-guardrails-evaluators.html), Hamel Husain and Shreya Shankar |
| Red-teaming as part of the eval loop | Module 10 | Hamel Husain and Shreya Shankar's [Maven course](https://maven.com/parlance-labs/evals) |

## Module 10 references

| Topic | Source |
|---|---|
| Risk taxonomy for LLM applications: prompt injection (LLM01), sensitive information disclosure (LLM02), excessive agency (LLM06), system prompt leakage (LLM07) | OWASP GenAI Security Project, [Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/): [LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), [LLM02](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/), [LLM06](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/), [LLM07](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/) |
| Prompt injection: the name, why it is hard, and why prompts alone do not fix it | Simon Willison, [Prompt injection attacks against GPT-3](https://simonwillison.net/2022/Sep/12/prompt-injection/) (2022) and his [prompt injection series](https://simonwillison.net/series/prompt-injection/) |
| The lethal trifecta: private data, untrusted content, external communication | Simon Willison, [The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (2025) |
| Separating privileged and quarantined models | Simon Willison, [The Dual LLM pattern for building AI assistants that can resist prompt injection](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/) (2023) |
| Indirect prompt injection through content an application retrieves | Greshake et al., [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/abs/2302.12173) (arXiv 2302.12173) |
| Spotlighting: marking untrusted input so the model can tell it apart | Hines et al., [Defending Against Indirect Prompt Injection Attacks With Spotlighting](https://arxiv.org/abs/2403.14720) (arXiv 2403.14720) |
| Constraining what a model that follows an injection can do; capability and control-flow designs | Beurer-Kellner et al., [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837) (arXiv 2506.08837); Debenedetti et al., [Defeating Prompt Injections by Design](https://arxiv.org/abs/2503.18813) (CaMeL, arXiv 2503.18813) |
| Measuring attacks and benign utility together on tool-using agents | Debenedetti et al., [AgentDojo](https://arxiv.org/abs/2406.13352) (arXiv 2406.13352) |
| Adversarial technique taxonomy for AI systems | MITRE [ATLAS](https://atlas.mitre.org/) |
| Generative AI risk management, including information security and confabulation | NIST, [AI 600-1: Generative Artificial Intelligence Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) (2024) |
| Argument injection and path traversal | MITRE [CWE-88](https://cwe.mitre.org/data/definitions/88.html); OWASP, [Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) |

The guarded agent, its tools and guardrails, the success checks, the report, and the red-team gate were written for
this course. The attack and benign cases, the model's turns, and the detector's verdicts are synthetic-authored
(`scripts/author_module10_fixtures.py`); the clips were generated with FFmpeg. All secrets are fake canaries and all
attacker hosts use the reserved `.example` domain. No real-world payloads are included.

## Module 9 references

| Topic | Source |
|---|---|
| CUSUM charts | E. S. Page, "Continuous Inspection Schemes", Biometrika 41 (1954), doi:10.1093/biomet/41.1-2.100; overview in [Wikipedia: CUSUM](https://en.wikipedia.org/wiki/CUSUM) |
| Control charts for proportions, and CUSUM in practice | NIST/SEMATECH e-Handbook of Statistical Methods: [attribute control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc332.htm) and [CUSUM control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm) |
| Cohen's kappa | J. Cohen, "A Coefficient of Agreement for Nominal Scales", Educational and Psychological Measurement 20 (1960), doi:10.1177/001316446002000104; overview in [Wikipedia: Cohen's kappa](https://en.wikipedia.org/wiki/Cohen%27s_kappa) |
| High agreement with low kappa | Feinstein and Cicchetti, [High agreement but low kappa: I. The problems of two paradoxes](https://pubmed.ncbi.nlm.nih.gov/2348207/), Journal of Clinical Epidemiology, 1990 |
| Weighting by inclusion probability | Horvitz and Thompson, "A Generalization of Sampling Without Replacement from a Finite Universe", JASA 47 (1952), doi:10.1080/01621459.1952.10483446; overview in [Wikipedia: Horvitz-Thompson estimator](https://en.wikipedia.org/wiki/Horvitz%E2%80%93Thompson_estimator) |
| Head and tail sampling of traces | [OpenTelemetry: Sampling](https://opentelemetry.io/docs/concepts/sampling/) |
| HTMX (vendored in `labs/annotate`, 0BSD licence) | [htmx documentation](https://htmx.org/docs/) and [source](https://github.com/bigskysoftware/htmx) |
| Testing the app without a server | [FastAPI: Testing](https://fastapi.tiangolo.com/tutorial/testing/) |

The sampling, drift, and agreement code, the annotation app, and the monitoring pages were written for this course.
The week of traffic, its feedback, the 40 AV1 traces, their labels, the judge verdicts on them, and both annotators'
labels are synthetic-authored (`scripts/author_module09_fixtures.py`); the model snapshot ids are fictional.

## Module 8 references

| Topic | Source |
|---|---|
| Job summaries (`$GITHUB_STEP_SUMMARY`) | [GitHub Docs: Workflow commands, adding a job summary](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary) |
| Workflow triggers (pull requests, labels, schedules, manual runs) | [GitHub Docs: Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) |
| Cancelling superseded runs | [GitHub Docs: Control the concurrency of workflows and jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) |
| Marking and selecting tests | [pytest: Working with custom markers](https://docs.pytest.org/en/stable/example/markers.html) |
| Record and replay of HTTP interactions (the "cassette" pattern) | [VCR.py documentation](https://vcrpy.readthedocs.io/en/latest/) |
| Ruling out a drop larger than a margin | [Equivalence test](https://en.wikipedia.org/wiki/Equivalence_test) (and non-inferiority testing) |
| Version numbers | [Semantic Versioning 2.0.0](https://semver.org/) |
| Reusing a holdout set adaptively | Dwork et al., [Generalization in Adaptive Data Analysis and Holdout Reuse](https://arxiv.org/abs/1506.02629) (arXiv 1506.02629) |
| How much test-set reuse hurts in practice | Recht et al., [Do ImageNet Classifiers Generalize to ImageNet?](https://arxiv.org/abs/1902.10811) (arXiv 1902.10811) |
| Leakage in ML evaluation | Kapoor and Narayanan, [Leakage and the Reproducibility Crisis in ML-based Science](https://arxiv.org/abs/2207.07048) (arXiv 2207.07048) |
| Benchmark contamination in LLMs | Sainz et al., [NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark](https://arxiv.org/abs/2310.18018) (arXiv 2310.18018) |

The gate rule, the golden manifest, the hygiene checks, and the workflow were written for this course. The 54 new
judge verdicts on prompt v2's answers are synthetic-authored (`scripts/author_module08_fixtures.py`); every other
output the gate replays comes from modules 5 and 6.

## Module 7 references

| Topic | Source |
|---|---|
| Precision and recall | [Precision and recall](https://en.wikipedia.org/wiki/Precision_and_recall) |
| Mean reciprocal rank | [Mean reciprocal rank](https://en.wikipedia.org/wiki/Mean_reciprocal_rank) |
| nDCG | [Discounted cumulative gain](https://en.wikipedia.org/wiki/Discounted_cumulative_gain) (Järvelin and Kekäläinen, 2002) |
| BM25 | [Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25) (Robertson and colleagues) |
| Images in Claude requests | [Anthropic: vision](https://platform.claude.com/docs/en/build-with-claude/vision) |
| Test frames and spectrograms | [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html) (`testsrc2`, `mandelbrot`, `smptehdbars`, `geq`, `lutrgb`, `showspectrumpic`) and libx264 |

The second-edition knowledge base (`data/kb_v2/`), the relevance labels, the chat scenarios, and the image labels
were written for this course. All module 7 model outputs (RAG answers, chat and simulated-user turns, planner and
specialist turns, judge verdicts, vision answers) and their labels are synthetic-authored
(`scripts/author_module07_fixtures.py`); they were not produced by running the models live. The retrieval metrics
are computed, not authored.

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
